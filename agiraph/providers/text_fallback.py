"""Text fallback adapter — for models without native tool calling.

Tools are injected into the prompt. Responses parsed from <tool_call> tags.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from agiraph.models import ModelResponse, ToolCall, ToolDef, TokenUsage
from agiraph.providers.base import ProviderAdapter

logger = logging.getLogger(__name__)


class TextFallbackAdapter(ProviderAdapter):
    """Wraps any text-only model, injecting tool schemas into the prompt."""

    def __init__(self, inner_adapter: ProviderAdapter):
        self.inner = inner_adapter

    def format_tools(self, tools: list[ToolDef]) -> None:
        # No structured tools — everything goes in the prompt
        return None

    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        lines = ["## Available Tools\n"]
        lines.append("To call a tool, output EXACTLY this format:")
        lines.append("```")
        lines.append('<tool_call>{"name": "tool_name", "arguments": {"key": "value"}}</tool_call>')
        lines.append("```\n")
        lines.append("You can make multiple tool calls in one response.\n")

        for t in tools:
            lines.append(f"### {t.name}")
            lines.append(f"**Description:** {t.description}")
            lines.append(f"**Parameters:** ```json\n{json.dumps(t.parameters, indent=2)}\n```")
            if t.guidance:
                lines.append(f"\n{t.guidance}\n")

        return "\n".join(lines)

    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDef] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        # Call the inner adapter without structured tools (they're in the prompt already)
        response = await self.inner.generate(
            messages=messages,
            tools=None,  # no structured tools
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Parse tool calls from the text
        if response.text:
            tool_calls = self._parse_tool_calls(response.text)
            clean_text = re.sub(r"<tool_call>.*?</tool_call>", "", response.text, flags=re.DOTALL).strip()
            return ModelResponse(
                text=clean_text or None,
                tool_calls=tool_calls,
                usage=response.usage,
                raw=response.raw,
            )
        return response

    def count_tokens(self, messages: list[dict]) -> int:
        return self.inner.count_tokens(messages)

    def _parse_tool_calls(self, text: str) -> list[ToolCall]:
        tool_calls = []
        for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
            try:
                parsed = json.loads(match.group(1).strip())
                tool_calls.append(
                    ToolCall(
                        name=parsed["name"],
                        args=parsed.get("arguments", parsed.get("args", {})),
                        id=f"tc_{uuid.uuid4().hex[:8]}",
                    )
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse tool call: {e}")
        return tool_calls
