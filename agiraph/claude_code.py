"""Claude Code CLI runner — treats the CLI as an inference service.

Spawns `claude -p` as a subprocess with stream-json output and
forwards events to Agiraph's EventBus.

Model strings: claude-code/opus, claude-code/sonnet, claude-code/haiku
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class ClaudeCodeEvent:
    """Parsed event from Claude Code stream-json output."""

    type: str  # "system", "assistant", "result"
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str | None:
        """Extract text content from assistant or result events."""
        if self.type == "assistant":
            msg = self.data.get("message", {})
            content = msg.get("content", [])
            texts = [b["text"] for b in content if b.get("type") == "text"]
            return "\n".join(texts) if texts else None
        if self.type == "result":
            return self.data.get("result")
        return None

    @property
    def tool_uses(self) -> list[dict]:
        """Extract tool_use blocks from assistant events."""
        if self.type != "assistant":
            return []
        msg = self.data.get("message", {})
        content = msg.get("content", [])
        return [b for b in content if b.get("type") == "tool_use"]

    @property
    def tool_results(self) -> list[dict]:
        """Extract tool_result blocks from assistant events."""
        if self.type != "assistant":
            return []
        msg = self.data.get("message", {})
        content = msg.get("content", [])
        return [b for b in content if b.get("type") == "tool_result"]

    @property
    def is_error(self) -> bool:
        if self.type == "result":
            return self.data.get("is_error", False)
        return False

    @property
    def cost_usd(self) -> float:
        if self.type == "result":
            return self.data.get("total_cost_usd", 0.0)
        return 0.0


def find_claude_binary() -> str:
    """Find the claude CLI binary."""
    path = shutil.which("claude")
    if not path:
        raise RuntimeError(
            "Claude Code CLI not found in PATH. "
            "Install it with: npm install -g @anthropic-ai/claude-code"
        )
    return path


def parse_claude_code_model(model_string: str) -> str:
    """Extract the sub-model from a claude-code/* model string.

    claude-code/opus -> opus
    claude-code/sonnet -> sonnet
    claude-code/haiku -> haiku
    claude-code -> sonnet (default)
    """
    if "/" in model_string:
        _, sub = model_string.split("/", 1)
        return sub or "sonnet"
    return "sonnet"


class ClaudeCodeRunner:
    """Runs Claude Code CLI as a subprocess and streams events."""

    def __init__(
        self,
        model: str = "sonnet",
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        max_budget_usd: float | None = None,
        skip_permissions: bool = True,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.max_budget_usd = max_budget_usd
        self.skip_permissions = skip_permissions
        self._process: asyncio.subprocess.Process | None = None

    def _build_command(self, prompt: str) -> list[str]:
        """Build the claude CLI command."""
        claude_path = find_claude_binary()

        cmd = [claude_path, "-p"]
        cmd.extend(["--output-format", "stream-json"])
        cmd.extend(["--model", self.model])
        cmd.append("--verbose")

        if self.skip_permissions:
            cmd.append("--dangerously-skip-permissions")

        if self.system_prompt:
            cmd.extend(["--system-prompt", self.system_prompt])

        if self.allowed_tools:
            cmd.extend(["--allowedTools", " ".join(self.allowed_tools)])

        if self.disallowed_tools:
            cmd.extend(["--disallowedTools", " ".join(self.disallowed_tools)])

        if self.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(self.max_budget_usd)])

        cmd.append(prompt)
        return cmd

    async def run(
        self,
        prompt: str,
        cwd: str | Path | None = None,
    ) -> AsyncIterator[ClaudeCodeEvent]:
        """Run Claude Code and yield events as they stream in."""
        cmd = self._build_command(prompt)

        logger.info(f"[ClaudeCode] Starting: claude -p --model {self.model} (cwd={cwd})")
        logger.debug(f"[ClaudeCode] Full command: {cmd}")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )

        assert self._process.stdout is not None

        while True:
            line = await self._process.stdout.readline()
            if not line:
                break

            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            try:
                data = json.loads(line_str)
                event_type = data.get("type", "unknown")
                yield ClaudeCodeEvent(type=event_type, data=data)
            except json.JSONDecodeError:
                logger.warning(f"[ClaudeCode] Non-JSON output: {line_str[:200]}")

        await self._process.wait()

        # Log stderr if any
        if self._process.stderr:
            stderr = await self._process.stderr.read()
            if stderr:
                stderr_text = stderr.decode("utf-8").strip()
                if stderr_text:
                    logger.warning(f"[ClaudeCode] stderr: {stderr_text[:500]}")

        if self._process.returncode != 0:
            logger.error(
                f"[ClaudeCode] Process exited with code {self._process.returncode}"
            )

    async def cancel(self):
        """Cancel the running process."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()


async def run_claude_code(
    prompt: str,
    cwd: str | Path | None = None,
    model: str = "sonnet",
    system_prompt: str | None = None,
    allowed_tools: list[str] | None = None,
    max_budget_usd: float | None = None,
) -> tuple[str, list[ClaudeCodeEvent]]:
    """Convenience: run Claude Code CLI and return (result_text, all_events)."""
    runner = ClaudeCodeRunner(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=allowed_tools,
        max_budget_usd=max_budget_usd,
    )

    events: list[ClaudeCodeEvent] = []
    result_text = ""

    async for event in runner.run(prompt, cwd=cwd):
        events.append(event)
        if event.type == "result":
            result_text = event.data.get("result", "")

    return result_text, events
