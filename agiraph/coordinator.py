"""Coordinator — the agent's brain. Runs as a harnessed node with special tools."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agiraph.models import ModelResponse, Stage, StageContract, WorkNode, Worker, generate_id
from agiraph.providers import create_provider
from agiraph.tools.context import ToolContext
from agiraph.worker import AutonomousWorkerExecutor, WorkerExecutor

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

    async def run(self):
        """Main coordinator loop — always responsive to human."""
        self.agent.status = "working"
        self.agent.event_bus.emit_simple("agent.started", self.agent.id, goal=self.agent.goal)

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
        max_coordinator_turns = 50
        for turn in range(max_coordinator_turns):
            if self.finished:
                break

            # Yield point: check for human messages
            await self._yield_point()

            try:
                response = await self.provider.generate(
                    messages=self.conversation,
                    tools=tools,
                    system=system,
                    max_tokens=4096,
                )
            except Exception as e:
                logger.error(f"Coordinator LLM call failed: {e}")
                await asyncio.sleep(3)
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
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._yield_point()

                    self.agent.event_bus.emit_simple(
                        "tool.called",
                        self.agent.id,
                        tool=tc.name,
                        args={k: str(v)[:100] for k, v in tc.args.items()},
                    )

                    # Special handling for spawn_worker + assign_worker — need to trigger scheduler
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

                    # After spawning/assigning workers, trigger the scheduler
                    if tc.name in ("assign_worker", "spawn_worker", "create_work_node"):
                        await self._maybe_launch_workers()

                    # Check for finish
                    if tc.name == "finish" or "AGENT_FINISHED" in result:
                        self.finished = True
                        self.agent.status = "completed"
                        break

                    # After reconvene, launch any new workers
                    if tc.name == "reconvene":
                        await self._maybe_launch_workers()
            else:
                # No tool calls — coordinator just spoke. Check if it should continue.
                pass

            # Monitor running workers and schedule new work
            await self._monitor_workers()

        if not self.finished:
            logger.warning(f"Coordinator hit max turns ({max_coordinator_turns})")
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

            if worker.type == "autonomous":
                executor = AutonomousWorkerExecutor(worker, node, ctx)
            else:
                executor = WorkerExecutor(worker, node, self.agent.registry, ctx)

            result = await executor.execute()
            logger.info(f"Node {node.id} completed by {worker.name}: {result[:100]}")
        except Exception as e:
            node.status = "failed"
            node.result = f"Execution error: {e}"
            logger.error(f"Node {node.id} failed: {e}", exc_info=True)
        finally:
            if worker.status == "busy":
                worker.status = "idle"
            self.agent._running_tasks.pop(node.id, None)

    async def _monitor_workers(self):
        """Brief monitoring pause — check for completed nodes."""
        # Wait briefly for any running workers
        if self.agent._running_tasks:
            await asyncio.sleep(1)

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
        await asyncio.sleep(0)

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
            "- For simple tasks, just work directly with tools — no need for workers.\n"
            "- For complex tasks, create work nodes and spawn workers.\n"
            "- Give workers clear, specific specs. Not 'look into this' but 'produce a 500-word analysis'.\n"
            "- After workers complete, use reconvene to assess and plan next steps.\n"
            "- Write important findings to files. Your conversation may be compacted.\n"
            "- Only ask the human when genuinely stuck.\n"
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
        return msg
