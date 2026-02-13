"""Coordinator — the agent's brain. Runs as a harnessed node with special tools."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agiraph.claude_code import ClaudeCodeRunner, parse_claude_code_model
from agiraph.models import ModelResponse, Stage, StageContract, WorkNode, Worker, generate_id
from agiraph.providers import create_provider
from agiraph.tools.context import ToolContext
from agiraph.worker import AutonomousWorkerExecutor, ClaudeCodeWorkerExecutor, WorkerExecutor

if TYPE_CHECKING:
    from agiraph.agent import Agent

logger = logging.getLogger(__name__)


class Coordinator:
    """The agent's coordinator — always-live loop that manages the work graph."""

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.provider = create_provider(agent.coordinator_model)
        self.conversation: list[dict] = []
        self.finished = False
        self._stopped = False  # Set by Agent.stop() — pauses loop, resumes on human input
        self._human_wakeup = asyncio.Event()  # Set when human sends a message

    @property
    def is_claude_code(self) -> bool:
        return self.agent.coordinator_model.startswith("claude-code")

    async def run(self):
        """Main coordinator loop — always responsive to human."""
        self.agent.status = "working"
        self.agent.event_bus.emit_simple("agent.started", self.agent.id, goal=self.agent.goal)

        # If using Claude Code CLI as coordinator, use the special path
        if self.is_claude_code:
            await self._run_claude_code()
            return

        system = self._build_system_prompt()
        tools = self.agent.registry.get_coordinator_tools()

        # Build the coordinator's tool context
        self.context = ToolContext(
            agent_id=self.agent.id,
            agent_path=self.agent.path,
            run_dir=self.agent.current_run_dir,
            node=None,
            worker=None,
            board=self.agent.board,
            worker_pool=self.agent.worker_pool,
            message_bus=self.agent.message_bus,
            event_bus=self.agent.event_bus,
            human_response_queue=self.agent.human_response_queue,
            trigger_store=self.agent.triggers,
            default_model=self.agent.coordinator_model,
        )

        # Initial prompt with the goal
        self.conversation = [
            {"role": "user", "content": f"Your goal:\n\n{self.agent.goal}"},
        ]

        # Main loop
        max_coordinator_turns = 200
        consecutive_errors = 0
        max_consecutive_errors = 5
        for turn in range(max_coordinator_turns):
            if self.finished:
                break

            # --- Handle STOP: inject context summary, wait for human ---
            if self._stopped:
                summary = self._build_context_summary()
                self.conversation.append({
                    "role": "user",
                    "content": summary,
                })
                logger.info("[Coordinator] Stopped — injected context summary, waiting for human...")
                self.agent.status = "waiting_for_human"
                # Wait for human to send a message
                while not self.finished:
                    self._human_wakeup.clear()
                    try:
                        await asyncio.wait_for(self._human_wakeup.wait(), timeout=60.0)
                    except asyncio.TimeoutError:
                        continue
                    # Check if there's an actual human message
                    await self._yield_point()
                    if any(
                        m.get("role") == "user" and m.get("content", "").startswith("[Message from human]")
                        for m in self.conversation[-5:]
                    ) or self.agent.message_bus.has_messages("coordinator"):
                        await self._yield_point()
                        break
                self._stopped = False
                self.agent.status = "working"
                if self.finished:
                    break
                logger.info("[Coordinator] Resumed after stop — human sent a message")

            # Yield point: check for human messages
            await self._yield_point()

            try:
                response = await self.provider.generate(
                    messages=self.conversation,
                    tools=tools,
                    system=system,
                    max_tokens=4096,
                )
                consecutive_errors = 0  # reset on success
            except Exception as e:
                consecutive_errors += 1
                backoff = min(3 * (2 ** (consecutive_errors - 1)), 60)  # 3s, 6s, 12s, 24s, 48s, 60s
                logger.error(f"Coordinator LLM call failed ({consecutive_errors}/{max_consecutive_errors}): {e}")
                self.agent.event_bus.emit_simple(
                    "tool.error", self.agent.id, error=str(e), source="coordinator"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Coordinator giving up after {max_consecutive_errors} consecutive LLM errors")
                    self.agent.status = "waiting_for_human"
                    self.agent.conversation_log.append({
                        "role": "coordinator",
                        "content": f"[Error] LLM provider failed {max_consecutive_errors} times in a row. Pausing until you send a message. Last error: {e}",
                        "ts": time.time(),
                    })
                    # Wait for human input before retrying
                    self._human_wakeup.clear()
                    try:
                        await asyncio.wait_for(self._human_wakeup.wait(), timeout=300.0)
                    except asyncio.TimeoutError:
                        pass
                    consecutive_errors = 0
                    self.agent.status = "working"
                else:
                    await asyncio.sleep(backoff)
                continue

            # Add to conversation
            assistant_msg = self._response_to_msg(response)
            self.conversation.append(assistant_msg)

            if response.text:
                logger.info(f"[Coordinator] {response.text[:200]}")
                # Send text to human conversation
                self.agent.conversation_log.append({
                    "role": "coordinator",
                    "content": response.text,
                    "ts": time.time(),
                })

            # Handle tool calls
            launched_workers = False
            if response.tool_calls:
                # Process ALL tool calls and append results before any yield point.
                # OpenAI requires all tool results to immediately follow the assistant
                # tool_calls message — injecting user messages in between causes 400s.
                post_actions: list[str] = []
                for tc in response.tool_calls:
                    self.agent.event_bus.emit_simple(
                        "tool.called",
                        self.agent.id,
                        tool=tc.name,
                        args={k: str(v)[:100] for k, v in tc.args.items()},
                    )

                    result = await self.agent.registry.dispatch(tc, self.context)

                    self.agent.event_bus.emit_simple(
                        "tool.result",
                        self.agent.id,
                        tool=tc.name,
                        result=result[:200],
                    )

                    self.conversation.append({
                        "role": "tool",
                        "tool_use_id": tc.id,
                        "id": tc.id,
                        "name": tc.name,
                        "content": result,
                    })

                    if tc.name in ("assign_worker", "spawn_worker", "create_work_node"):
                        post_actions.append("launch_workers")

                    if tc.name == "finish" or "AGENT_FINISHED" in result:
                        self.finished = True
                        self.agent.status = "completed"
                        break

                    if tc.name == "reconvene":
                        post_actions.append("launch_workers")

                # Now safe to yield and run post-actions (all tool results are appended)
                await self._yield_point()
                if "launch_workers" in post_actions:
                    await self._maybe_launch_workers()
                    launched_workers = True
            else:
                # No tool calls — coordinator just spoke text.
                # WAIT for human input or worker completion before looping.
                # Without this, the coordinator would loop endlessly repeating itself.
                pass

            # ---------------------------------------------------------------
            # KEY FIX: Wait for something to happen before next LLM call.
            # Without this, the coordinator calls the LLM repeatedly with
            # the same state and gets duplicate outputs.
            # ---------------------------------------------------------------
            if not self.finished:
                await self._wait_for_activity(
                    workers_running=launched_workers or bool(self.agent._running_tasks)
                )

        if not self.finished:
            logger.warning(f"Coordinator hit max turns ({max_coordinator_turns})")
            self.agent.status = "completed"

        self.agent.event_bus.emit_simple("agent.completed", self.agent.id)

    async def _run_claude_code(self):
        """Run the coordinator using Claude Code CLI instead of the ReAct loop.

        Claude Code handles its own tool dispatch (Read, Write, Bash, etc.),
        so we just pass it the goal and stream its output as events.
        """
        sub_model = parse_claude_code_model(self.agent.coordinator_model)
        system = self._build_system_prompt()

        runner = ClaudeCodeRunner(
            model=sub_model,
            system_prompt=system,
            skip_permissions=True,
        )

        logger.info(f"[Coordinator] Using Claude Code CLI (model={sub_model})")

        result_text = ""
        try:
            async for event in runner.run(
                prompt=f"Your goal:\n\n{self.agent.goal}",
                cwd=str(self.agent.current_run_dir),
            ):
                if event.type == "system":
                    self.agent.event_bus.emit_simple(
                        "claude_code.init",
                        self.agent.id,
                        session_id=event.data.get("session_id", ""),
                        model=event.data.get("model", ""),
                        tools=event.data.get("tools", []),
                    )

                elif event.type == "assistant":
                    # Forward text content
                    text = event.text
                    if text:
                        logger.info(f"[Coordinator:ClaudeCode] {text[:200]}")
                        self.agent.conversation_log.append({
                            "role": "coordinator",
                            "content": text,
                            "ts": time.time(),
                        })

                    # Forward tool uses as events
                    for tu in event.tool_uses:
                        tool_name = tu.get("name", "unknown")
                        tool_input = tu.get("input", {})
                        self.agent.event_bus.emit_simple(
                            "tool.called",
                            self.agent.id,
                            tool=f"cc:{tool_name}",
                            args={k: str(v)[:100] for k, v in tool_input.items()}
                            if isinstance(tool_input, dict)
                            else {},
                        )

                    # Forward tool results as events
                    for tr in event.tool_results:
                        content = tr.get("content", "")
                        if isinstance(content, list):
                            content = " ".join(
                                b.get("text", "") for b in content if isinstance(b, dict)
                            )
                        self.agent.event_bus.emit_simple(
                            "tool.result",
                            self.agent.id,
                            tool="cc:tool_result",
                            result=str(content)[:200],
                        )

                elif event.type == "result":
                    result_text = event.data.get("result", "")
                    cost = event.data.get("total_cost_usd", 0)
                    duration = event.data.get("duration_ms", 0)
                    self.agent.event_bus.emit_simple(
                        "claude_code.result",
                        self.agent.id,
                        result=result_text[:500],
                        cost_usd=cost,
                        duration_ms=duration,
                        is_error=event.is_error,
                    )
                    if result_text:
                        self.agent.conversation_log.append({
                            "role": "coordinator",
                            "content": f"[Result] {result_text}",
                            "ts": time.time(),
                        })

        except Exception as e:
            logger.error(f"[Coordinator:ClaudeCode] Error: {e}", exc_info=True)
            self.agent.event_bus.emit_simple(
                "tool.error", self.agent.id, error=str(e), source="claude_code"
            )

        self.agent.status = "completed"
        self.agent.event_bus.emit_simple("agent.completed", self.agent.id)

    async def _maybe_launch_workers(self):
        """Check board for assigned nodes and launch worker execution."""
        for node in self.agent.board.nodes.values():
            if node.status == "assigned" and node.assigned_worker:
                worker = self.agent.worker_pool.get(node.assigned_worker)
                if worker and worker.status == "busy":
                    # Already launching or need to launch
                    if node.id not in self.agent._running_tasks:
                        task = asyncio.create_task(self._execute_node(worker, node))
                        self.agent._running_tasks[node.id] = task

    async def _execute_node(self, worker: Worker, node: WorkNode):
        """Execute a single node with its assigned worker."""
        try:
            ctx = ToolContext(
                agent_id=self.agent.id,
                agent_path=self.agent.path,
                run_dir=self.agent.current_run_dir,
                node=node,
                worker=worker,
                board=self.agent.board,
                worker_pool=self.agent.worker_pool,
                message_bus=self.agent.message_bus,
                event_bus=self.agent.event_bus,
                human_response_queue=self.agent.human_response_queue,
                trigger_store=self.agent.triggers,
                default_model=self.agent.coordinator_model,
            )

            if worker.type == "claude_code":
                executor = ClaudeCodeWorkerExecutor(worker, node, ctx)
            elif worker.type == "autonomous":
                executor = AutonomousWorkerExecutor(worker, node, ctx)
            else:
                executor = WorkerExecutor(worker, node, self.agent.registry, ctx)

            result = await executor.execute()
            logger.info(f"Node {node.id} completed by {worker.name}: {result[:100]}")
        except asyncio.CancelledError:
            node.status = "failed"
            node.result = "Stopped by user"
            logger.info(f"Node {node.id} cancelled (stopped)")
        except Exception as e:
            node.status = "failed"
            node.result = f"Execution error: {e}"
            logger.error(f"Node {node.id} failed: {e}", exc_info=True)
        finally:
            if worker.status == "busy":
                worker.status = "idle"
            self.agent._running_tasks.pop(node.id, None)
            # Wake coordinator so it can process worker completion
            self._human_wakeup.set()

    async def _wait_for_activity(self, workers_running: bool = False):
        """Wait until something interesting happens before next LLM call.

        This prevents the coordinator from calling the LLM in a tight loop
        with the same state, which causes duplicate/repeated outputs.

        Wakes up when:
        - A human message arrives
        - A worker completes (node status changes)
        - Periodic timeout for status checks
        """
        if self.finished:
            return

        if workers_running or self.agent._running_tasks:
            # Workers are running — poll for completion or human messages
            logger.info("[Coordinator] Waiting for workers to complete...")
            while self.agent._running_tasks and not self.finished:
                self._human_wakeup.clear()
                try:
                    await asyncio.wait_for(self._human_wakeup.wait(), timeout=2.0)
                    # Woken by human message — break to handle it
                    logger.info("[Coordinator] Woken by human message")
                    break
                except asyncio.TimeoutError:
                    pass
                # Check if any workers completed
                await self._yield_point()
        else:
            # No workers running and coordinator just spoke — wait for human
            logger.info("[Coordinator] Waiting for human input...")
            self.agent.status = "waiting_for_human"
            self._human_wakeup.clear()
            try:
                # Wait up to 60s for human input, then do a status check
                await asyncio.wait_for(self._human_wakeup.wait(), timeout=60.0)
                logger.info("[Coordinator] Received human input")
            except asyncio.TimeoutError:
                logger.info("[Coordinator] Timeout waiting for human, doing status check")
            if self.agent.status == "waiting_for_human":
                self.agent.status = "working"

    async def _monitor_workers(self):
        """Brief monitoring pause — check for completed nodes."""
        # Just a quick yield, actual waiting is done in _wait_for_activity
        await asyncio.sleep(0)

    async def _yield_point(self):
        """Check for incoming messages."""
        if self.agent.message_bus:
            messages = self.agent.message_bus.receive("coordinator")
            if messages:
                for msg in messages:
                    self.conversation.append({
                        "role": "user",
                        "content": f"[Message from {msg.from_id}]: {msg.content}",
                    })
                    # Only log non-human messages — human messages are already
                    # logged by agent.send_message() to avoid duplicates
                    if msg.from_id != "human":
                        self.agent.conversation_log.append({
                            "role": msg.from_id,
                            "to": "coordinator",
                            "content": msg.content,
                            "ts": time.time(),
                        })

            # Also check for human messages
            human_msgs = self.agent.message_bus.receive("human_to_coordinator")
            for msg in human_msgs:
                self.conversation.append({
                    "role": "user",
                    "content": f"[Human]: {msg.content}",
                })
                # Wake up the coordinator if waiting
                self._human_wakeup.set()
        await asyncio.sleep(0)

    def notify_human_message(self):
        """External call to wake up the coordinator when a human message arrives."""
        self._human_wakeup.set()

    def _build_context_summary(self) -> str:
        """Build a succinct summary of what happened for resuming after STOP."""
        parts = [
            "[System] The user stopped execution. All workers have been halted.",
            "Here is the current state of work — use this to answer questions or continue.\n",
        ]

        # Board state
        nodes = self.agent.board.nodes
        if nodes:
            parts.append("## Work Board")
            for node in nodes.values():
                icons = {"completed": "+", "failed": "X", "running": "~", "pending": ".", "assigned": ">"}
                icon = icons.get(node.status, "?")
                line = f"  [{icon}] {node.id}: {node.task[:80]} — {node.status}"
                if node.result:
                    line += f"\n      Result: {node.result[:300]}"
                parts.append(line)

        # Workers
        workers = self.agent.worker_pool.workers
        if workers:
            parts.append("\n## Team")
            for w in workers.values():
                parts.append(f"  - {w.name} ({w.role}, {w.type}) — {w.status}")

        parts.append("\nThe user may now give further instructions. Respond helpfully with full context of what was accomplished and what remains.")
        return "\n".join(parts)

    def _build_system_prompt(self) -> str:
        """Assemble the coordinator's system prompt."""
        sections = []

        # Identity (SOUL.md)
        soul_file = self.agent.path / "SOUL.md"
        if soul_file.exists():
            sections.append(soul_file.read_text())
        else:
            sections.append(
                "# You Are The Coordinator\n\n"
                "You've been given a goal. Your job is to get it done — well, completely, and efficiently.\n\n"
                "You can work alone on simple tasks or spawn a team of workers for complex ones.\n"
                "Use create_work_node to define tasks, spawn_worker to create workers, "
                "and assign_worker to connect them.\n"
                "Workers will execute and publish results. Use check_board to monitor progress.\n"
                "When done, call finish() with a summary."
            )

        # Goal
        sections.append(f"## Goal\n\n{self.agent.goal}")

        # Date
        sections.append(f"Today is {date.today()}")

        # Mode
        if self.agent.mode == "finite":
            sections.append(
                "## Mode: Finite Game\n\n"
                "Work until the goal is fully achieved, then call finish()."
            )
        else:
            sections.append(
                "## Mode: Infinite Game\n\n"
                "This is an ongoing mission. Work in cycles. Checkpoint between them. "
                "Never conclude — keep going."
            )

        # Agent memory
        memory_file = self.agent.path / "MEMORY.md"
        if memory_file.exists():
            mem = memory_file.read_text().strip()
            if mem:
                sections.append(f"## Your Memory\n\n{mem}")

        # Operating rules
        sections.append(
            "## Operating Rules\n\n"
            "You are the COORDINATOR — a responsive manager, NOT a worker.\n\n"
            "### Responsiveness (CRITICAL)\n"
            "- Always respond to human messages immediately with context-aware replies.\n"
            "- Never do heavy work yourself. Delegate to workers.\n"
            "- Your main job: triage requests, plan work, spawn workers, monitor progress, report to human.\n"
            "- When the human asks a question, answer it from your existing context.\n"
            "- When the human gives a new task, create work nodes and assign workers.\n\n"
            "### Delegation\n"
            "- For ANY task that requires reading files, writing code, searching, or analysis: create a work node and spawn a worker.\n"
            "- Give workers clear, specific specs. Not 'look into this' but 'produce a 500-word analysis of X'.\n"
            "- After workers complete, use reconvene to assess results and plan next steps.\n"
            "- Only use tools directly for quick checks (check_board, send_message).\n\n"
            "### Communication\n"
            "- Keep the human informed. Summarize worker progress.\n"
            "- When asked 'what's happening?', report the current board state.\n"
            "- Write important findings to files. Your conversation may be compacted.\n"
            "- When the goal is met, call finish().\n"
        )

        return "\n\n---\n\n".join(sections)

    def _response_to_msg(self, response: ModelResponse) -> dict:
        msg: dict[str, Any] = {"role": "assistant"}
        if response.text:
            msg["content"] = response.text
        if response.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "args": tc.args}
                for tc in response.tool_calls
            ]
        if not msg.get("content") and not msg.get("tool_calls"):
            msg["content"] = ""
        # Preserve raw content blocks for multi-turn (web search results)
        if response.content_blocks:
            msg["_content_blocks"] = response.content_blocks
        return msg
