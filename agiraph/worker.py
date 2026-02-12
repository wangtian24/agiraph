"""Worker execution — harnessed (ReAct loop) and autonomous (subprocess)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agiraph.models import ModelResponse, ToolCall, WorkNode, Worker
from agiraph.providers import create_provider
from agiraph.tools.context import ToolContext

if TYPE_CHECKING:
    from agiraph.events import EventBus
    from agiraph.message_bus import MessageBus
    from agiraph.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Executes a work node using a harnessed worker (ReAct loop)."""

    def __init__(
        self,
        worker: Worker,
        node: WorkNode,
        registry: ToolRegistry,
        context: ToolContext,
    ):
        self.worker = worker
        self.node = node
        self.registry = registry
        self.context = context
        self.provider = create_provider(worker.model or "anthropic/claude-sonnet-4-5")
        self.conversation: list[dict] = []
        self.finished = False

    async def execute(self) -> str:
        """Run the ReAct loop until publish, max iterations, or error."""
        self.node.status = "running"
        self.worker.status = "busy"

        self.context.emit(
            "node.started",
            node_id=self.node.id,
            worker_id=self.worker.id,
            worker_name=self.worker.name,
        )

        # Build system prompt
        system = self._build_system_prompt()
        tools = self.registry.get_worker_tools()

        # Initial user message with the spec
        self.conversation = [
            {"role": "user", "content": self._build_initial_message()},
        ]

        for iteration in range(self.worker.max_iterations):
            # Yield point: check messages
            await self._yield_point()

            if self.finished:
                break

            try:
                response = await self.provider.generate(
                    messages=self.conversation,
                    tools=tools,
                    system=system,
                    max_tokens=4096,
                )
            except asyncio.CancelledError:
                # STOP pressed — exit gracefully
                self._save_failure_notes("Stopped by user", "")
                self.node.status = "failed"
                self.node.result = "Stopped by user"
                self.worker.status = "idle"
                return self.node.result
            except Exception as e:
                logger.error(f"LLM call failed for {self.worker.name}: {e}")
                self.context.emit("tool.error", error=str(e), worker=self.worker.name)
                # Wait and retry once
                await asyncio.sleep(2)
                try:
                    response = await self.provider.generate(
                        messages=self.conversation,
                        tools=tools,
                        system=system,
                        max_tokens=4096,
                    )
                except asyncio.CancelledError:
                    self._save_failure_notes("Stopped by user", "")
                    self.node.status = "failed"
                    self.node.result = "Stopped by user"
                    self.worker.status = "idle"
                    return self.node.result
                except Exception as e2:
                    # Retry failed — save notes and notify coordinator
                    notes = self._save_failure_notes(str(e), str(e2))
                    if self.context.message_bus:
                        self.context.message_bus.send(
                            self.worker.name,
                            "coordinator",
                            f"[WORKER FAILED] {self.worker.name} failed on node [{self.node.id}].\n"
                            f"Task: {self.node.task[:200]}\n"
                            f"Error: {e2}\n"
                            f"Worker notes:\n{notes[:1500]}",
                        )
                    self.context.emit(
                        "node.failed",
                        node_id=self.node.id,
                        worker_name=self.worker.name,
                        error=str(e2),
                    )
                    self.node.status = "failed"
                    self.node.result = f"LLM call failed: {e2}"
                    self.worker.status = "idle"
                    return self.node.result

            # Add assistant response to conversation
            assistant_msg = self._response_to_msg(response)
            self.conversation.append(assistant_msg)

            # Log any text output
            if response.text:
                logger.info(f"[{self.worker.name}] {response.text[:200]}")

            # Handle tool calls
            if response.tool_calls:
                for tc in response.tool_calls:
                    await self._yield_point()

                    self.context.emit(
                        "tool.called",
                        tool=tc.name,
                        worker=self.worker.name,
                        args={k: str(v)[:100] for k, v in tc.args.items()},
                    )

                    try:
                        result = await self.registry.dispatch(tc, self.context)
                    except asyncio.CancelledError:
                        self._save_failure_notes("Stopped by user during tool dispatch", "")
                        self.node.status = "failed"
                        self.node.result = "Stopped by user"
                        self.worker.status = "idle"
                        return self.node.result
                    except Exception as tool_err:
                        result = f"[Tool error] {tc.name}: {tool_err}"
                        self.context.emit("tool.error", tool=tc.name, error=str(tool_err), worker=self.worker.name)

                    self.context.emit(
                        "tool.result",
                        tool=tc.name,
                        worker=self.worker.name,
                        result=result[:200],
                    )

                    self.conversation.append({
                        "role": "tool",
                        "tool_use_id": tc.id,
                        "id": tc.id,
                        "name": tc.name,
                        "content": result,
                    })

                    # Check for terminal tools
                    if tc.name == "publish":
                        self.finished = True
                        return result
                    if "AGENT_FINISHED" in result:
                        self.finished = True
                        return result
            else:
                # No tool calls — model just responded with text
                # This might happen if the model is done or confused
                if not response.text:
                    break

            # Log conversation for the node
            self._log_iteration(iteration, response)

        # Reached max iterations without publishing
        if not self.finished:
            notes = self._save_failure_notes("Max iterations reached", "")
            if self.context.message_bus:
                self.context.message_bus.send(
                    self.worker.name,
                    "coordinator",
                    f"[WORKER FAILED] {self.worker.name} hit max iterations on node [{self.node.id}].\n"
                    f"Task: {self.node.task[:200]}\n"
                    f"Worker notes:\n{notes[:1500]}",
                )
            self.context.emit(
                "node.failed",
                node_id=self.node.id,
                worker_name=self.worker.name,
                error="Max iterations reached",
            )
            self.node.status = "failed"
            self.node.result = f"Max iterations ({self.worker.max_iterations}) reached without publishing."
            self.worker.status = "idle"
            logger.warning(f"[{self.worker.name}] Max iterations reached on node {self.node.id}")
            return self.node.result

        return self.node.result or "Completed."

    def _build_system_prompt(self) -> str:
        """Build the worker's system prompt from identity, memory, and assignment."""
        sections = []

        # Worker identity
        if self.worker.worker_dir:
            identity_file = self.worker.worker_dir / "identity.md"
            if identity_file.exists():
                sections.append(identity_file.read_text())

        # Worker memory
        if self.worker.worker_dir:
            memory_file = self.worker.worker_dir / "memory.md"
            if memory_file.exists():
                mem = memory_file.read_text().strip()
                if mem:
                    sections.append(f"## Your Memory (From Past Work)\n\n{mem}")

        # Operating rules
        sections.append(
            "## Operating Rules\n\n"
            "- Write important findings to files (scratch/). Your conversation may be compacted.\n"
            "- Call publish() when your work is done. This moves scratch/ to published/.\n"
            "- Check messages periodically with check_messages.\n"
            "- Be specific in outputs. Quality over speed.\n"
            "- If stuck after 3 attempts, message the coordinator or ask the human.\n"
        )

        return "\n\n---\n\n".join(sections)

    def _build_initial_message(self) -> str:
        """Build the initial user message with the task spec."""
        parts = [f"## Your Assignment\n\n{self.node.task}"]

        # Include refs
        if self.node.refs and self.node.data_dir:
            refs_content = []
            for ref_name, ref_path in self.node.refs.items():
                full_path = self.context.run_dir / ref_path if self.context.run_dir else Path(ref_path)
                if full_path.exists():
                    content = full_path.read_text()
                    if len(content) > 5000:
                        content = content[:5000] + "\n[... truncated ...]"
                    refs_content.append(f"### {ref_name}\n\n{content}")
            if refs_content:
                parts.append("## Input Data (From Upstream Nodes)\n\n" + "\n\n---\n\n".join(refs_content))

        # Workspace info
        if self.node.data_dir:
            parts.append(
                f"## Your Workspace\n\n"
                f"- Scratch dir: nodes/{self.node.id}/scratch/ (write WIP here)\n"
                f"- Published dir: nodes/{self.node.id}/published/ (populated by publish())\n"
            )

        return "\n\n".join(parts)

    async def _yield_point(self):
        """Check for incoming messages before continuing."""
        if self.context.message_bus:
            messages = self.context.message_bus.receive(self.worker.name)
            if messages:
                for msg in messages:
                    self.conversation.append({
                        "role": "user",
                        "content": f"[Message from {msg.from_id}]: {msg.content}",
                    })
        await asyncio.sleep(0)

    def _response_to_msg(self, response: ModelResponse) -> dict:
        """Convert ModelResponse to a conversation message dict."""
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

    def _save_failure_notes(self, error1: str, error2: str) -> str:
        """Save the worker's accumulated work to a failure notes file."""
        parts = [
            f"# Failure Report — {self.worker.name}",
            f"**Node**: {self.node.id}",
            f"**Task**: {self.node.task}",
        ]
        if error1:
            parts.append(f"**First error**: {error1}")
        if error2:
            parts.append(f"**Second error**: {error2}")

        parts.append(f"\n## Conversation ({len(self.conversation)} messages)")
        for msg in self.conversation:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(f"**[{role}]** {content[:500]}")
            elif msg.get("tool_calls"):
                calls = msg["tool_calls"]
                for tc in calls:
                    parts.append(f"**[{role}:tool_call]** {tc.get('name', '?')}({json.dumps(tc.get('args', {}))[:200]})")

        notes = "\n\n".join(parts)

        if self.node.data_dir:
            self.node.data_dir.mkdir(parents=True, exist_ok=True)
            (self.node.data_dir / "failure_notes.md").write_text(notes)

        return notes[:2000]

    def _log_iteration(self, iteration: int, response: ModelResponse):
        """Log iteration to the node's log file."""
        if self.node.data_dir:
            log_file = self.node.data_dir / "log.jsonl"
            entry = {
                "iteration": iteration,
                "ts": time.time(),
                "worker": self.worker.name,
                "text": response.text[:200] if response.text else None,
                "tool_calls": [tc.name for tc in response.tool_calls],
                "usage": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
            }
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")


class ClaudeCodeWorkerExecutor:
    """Executes a work node using Claude Code CLI with stream-json output."""

    def __init__(
        self,
        worker: Worker,
        node: WorkNode,
        context: ToolContext,
    ):
        self.worker = worker
        self.node = node
        self.context = context

    async def execute(self) -> str:
        """Launch Claude Code CLI, stream events, return result."""
        from agiraph.claude_code import ClaudeCodeRunner, parse_claude_code_model

        self.node.status = "running"
        self.worker.status = "busy"

        self.context.emit(
            "node.started",
            node_id=self.node.id,
            worker_id=self.worker.id,
            worker_name=self.worker.name,
        )

        # Work directory: node's scratch dir
        work_dir = self.node.data_dir / "scratch" if self.node.data_dir else Path("./scratch")
        work_dir.mkdir(parents=True, exist_ok=True)

        # Write task file for reference
        (work_dir / "_task.md").write_text(self.node.task)

        # Build system prompt
        system_parts = [
            f"# Worker: {self.worker.name}",
            f"You are a worker executing a specific task. Work in the current directory.",
            f"Write your output files here. When done, create a _result.md summarizing your work.",
        ]
        if self.worker.capabilities:
            system_parts.append(f"Your capabilities: {', '.join(self.worker.capabilities)}")

        sub_model = parse_claude_code_model(self.worker.model or "claude-code/sonnet")

        runner = ClaudeCodeRunner(
            model=sub_model,
            system_prompt="\n\n".join(system_parts),
            skip_permissions=True,
        )

        self.context.emit(
            "worker.launched",
            worker=self.worker.name,
            command=f"claude -p --model {sub_model}",
        )

        result_text = ""
        try:
            async for event in runner.run(prompt=self.node.task, cwd=str(work_dir)):
                if event.type == "assistant":
                    text = event.text
                    if text:
                        logger.info(f"[{self.worker.name}:ClaudeCode] {text[:200]}")

                    for tu in event.tool_uses:
                        self.context.emit(
                            "tool.called",
                            tool=f"cc:{tu.get('name', '?')}",
                            worker=self.worker.name,
                            args={k: str(v)[:100] for k, v in tu.get("input", {}).items()}
                            if isinstance(tu.get("input"), dict)
                            else {},
                        )

                elif event.type == "result":
                    result_text = event.data.get("result", "")
                    cost = event.data.get("total_cost_usd", 0)
                    logger.info(
                        f"[{self.worker.name}:ClaudeCode] Done. "
                        f"Cost: ${cost:.4f}, Result: {result_text[:100]}"
                    )

        except asyncio.CancelledError:
            self.node.status = "failed"
            self.node.result = "Stopped by user"
            self.worker.status = "idle"
            return self.node.result
        except Exception as e:
            self.node.status = "failed"
            self.node.result = f"Claude Code error: {e}"
            self.worker.status = "idle"
            self.context.emit(
                "tool.error", error=str(e), worker=self.worker.name
            )
            self.context.emit(
                "node.failed",
                node_id=self.node.id,
                worker_name=self.worker.name,
                error=str(e),
            )
            if self.context.message_bus:
                self.context.message_bus.send(
                    self.worker.name,
                    "coordinator",
                    f"[WORKER FAILED] {self.worker.name} (Claude Code) failed on node [{self.node.id}].\n"
                    f"Task: {self.node.task[:200]}\nError: {e}",
                )
            return self.node.result

        # Check for _result.md (Claude Code may have written it)
        result_file = work_dir / "_result.md"
        if result_file.exists():
            result_text = result_file.read_text()

        if result_text:
            self.node.status = "completed"
            self.node.result = result_text
            self.context.emit(
                "node.completed",
                node_id=self.node.id,
                worker_name=self.worker.name,
                summary=result_text[:200],
            )
        else:
            self.node.status = "failed"
            self.node.result = "Claude Code completed but produced no result."

        self.worker.status = "idle"
        return self.node.result or "No result."


class AutonomousWorkerExecutor:
    """Executes a work node using an external agent (e.g., Claude Code CLI)."""

    POLL_INTERVAL = 5  # seconds

    def __init__(
        self,
        worker: Worker,
        node: WorkNode,
        context: ToolContext,
    ):
        self.worker = worker
        self.node = node
        self.context = context

    async def execute(self) -> str:
        """Launch external agent, monitor for completion."""
        self.node.status = "running"
        self.worker.status = "busy"

        task_dir = self.node.data_dir / "scratch" if self.node.data_dir else Path("./scratch")
        task_dir.mkdir(parents=True, exist_ok=True)

        # Write task files
        (task_dir / "_task.md").write_text(self.node.task)
        if self.node.refs:
            (task_dir / "_context.json").write_text(json.dumps(self.node.refs))
        (task_dir / "_inbox.md").write_text("")
        (task_dir / "_outbox.md").write_text("")

        # Build command
        cmd = self._build_command(task_dir)
        self.context.emit("worker.launched", worker=self.worker.name, command=" ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(task_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Monitor
            while proc.returncode is None:
                # Bridge messages
                self._bridge_messages(task_dir)

                # Check for result
                result_file = task_dir / "_result.md"
                if result_file.exists():
                    result = result_file.read_text()
                    proc.terminate()
                    await self._promote_to_published(task_dir)
                    self.node.status = "completed"
                    self.node.result = result
                    self.worker.status = "idle"
                    return result

                await asyncio.sleep(self.POLL_INTERVAL)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

            # Process exited
            result_file = task_dir / "_result.md"
            if result_file.exists():
                result = result_file.read_text()
                await self._promote_to_published(task_dir)
                self.node.status = "completed"
                self.node.result = result
                self.worker.status = "idle"
                return result

            # No result file — check stdout
            stdout = (await proc.stdout.read()).decode() if proc.stdout else ""
            self.node.status = "failed"
            self.node.result = f"Autonomous worker exited without _result.md.\nStdout: {stdout[:1000]}"
            self.worker.status = "idle"
            return self.node.result

        except Exception as e:
            self.node.status = "failed"
            self.node.result = f"Autonomous worker error: {e}"
            self.worker.status = "idle"
            return self.node.result

    def _build_command(self, task_dir: Path) -> list[str]:
        """Build the command to launch the external agent."""
        if self.worker.agent_command:
            return self.worker.agent_command.split()

        # Default: Claude Code CLI
        return [
            "claude", "-p", self.node.task,
            "--output-dir", str(task_dir),
        ]

    def _bridge_messages(self, task_dir: Path):
        """Bridge messages between message bus and file-based inbox/outbox."""
        # Deliver inbox
        if self.context.message_bus:
            messages = self.context.message_bus.receive(self.worker.name)
            if messages:
                inbox = task_dir / "_inbox.md"
                with open(inbox, "a") as f:
                    for msg in messages:
                        f.write(f"FROM: {msg.from_id}\n{msg.content}\n---\n")

        # Read outbox
        outbox = task_dir / "_outbox.md"
        if outbox.exists():
            content = outbox.read_text()
            if content.strip():
                for block in content.split("---"):
                    block = block.strip()
                    if not block:
                        continue
                    lines = block.split("\n")
                    to = "coordinator"
                    msg_content = block
                    for line in lines:
                        if line.startswith("TO:"):
                            to = line[3:].strip()
                            msg_content = "\n".join(l for l in lines if not l.startswith("TO:"))
                            break
                    if self.context.message_bus:
                        self.context.message_bus.send(self.worker.name, to, msg_content)
                # Clear outbox
                outbox.write_text("")

    async def _promote_to_published(self, task_dir: Path):
        """Move relevant files from scratch to published."""
        if not self.node.data_dir:
            return
        published = self.node.data_dir / "published"
        published.mkdir(parents=True, exist_ok=True)
        for f in task_dir.iterdir():
            if f.name.startswith("_"):
                continue  # skip metadata files
            dest = published / f.name
            if f.is_dir():
                shutil.copytree(f, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(f, dest)
