"""Anthropic (Claude) provider adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from agiraph.config import ANTHROPIC_API_KEY, NATIVE_SEARCH_MAX_USES
from agiraph.models import ModelResponse, ToolCall, ToolDef, TokenUsage
from agiraph.providers.base import ProviderAdapter

logger = logging.getLogger(__name__)


class AnthropicAdapter(ProviderAdapter):
    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        lines = ["## Tool Usage Guide\n"]
        for t in tools:
            if t.guidance:
                lines.append(f"### {t.name}\n{t.guidance}\n")
        return "\n".join(lines)

    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDef] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system:
            kwargs["system"] = system

        if tools:
            formatted_tools = self.format_tools(tools)
            # Add native web search — all Anthropic models support it
            formatted_tools.append({
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": NATIVE_SEARCH_MAX_USES,
            })
            kwargs["tools"] = formatted_tools

        try:
            raw = await self.client.messages.create(**kwargs)
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise

        return self._parse_response(raw)

    def count_tokens(self, messages: list[dict]) -> int:
        # Rough estimate: 4 chars per token
        total = sum(len(json.dumps(m)) for m in messages)
        return total // 4

    def _format_messages(self, messages: list[dict]) -> list[dict]:
        """Convert our internal format to Anthropic's format."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue  # system messages go via the system parameter
            if role == "tool":
                formatted.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_use_id", msg.get("id", "unknown")),
                            "content": str(msg.get("content", "")),
                        }
                    ],
                })
            elif role == "assistant":
                # If we stored raw content blocks (e.g., from web search turn),
                # pass them through directly to preserve encrypted search results.
                raw_blocks = msg.get("_content_blocks")
                if raw_blocks:
                    formatted.append({"role": "assistant", "content": raw_blocks})
                else:
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])
                    blocks: list[dict] = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", "unknown"),
                            "name": tc.get("name", ""),
                            "input": tc.get("args", tc.get("input", {})),
                        })
                    formatted.append({"role": "assistant", "content": blocks if blocks else content or ""})
            else:
                formatted.append({"role": "user", "content": str(msg.get("content", ""))})
        return formatted

    def _parse_response(self, raw: Any) -> ModelResponse:
        tool_calls = []
        text_parts = []
        has_search = False

        for block in raw.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(name=block.name, args=block.input, id=block.id))
            elif block.type == "text":
                text_parts.append(block.text)
            elif block.type in ("server_tool_use", "web_search_tool_result"):
                has_search = True
                if block.type == "server_tool_use":
                    query = getattr(block, "input", {}).get("query", "") if hasattr(block, "input") else ""
                    logger.info(f"[WebSearch] query: {query}")

        # Store raw content blocks for multi-turn if web search was used
        content_blocks = None
        if has_search:
            content_blocks = []
            for block in raw.content:
                try:
                    content_blocks.append(block.model_dump())
                except Exception:
                    content_blocks.append({"type": getattr(block, "type", "unknown")})

        return ModelResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            usage=TokenUsage(raw.usage.input_tokens, raw.usage.output_tokens),
            raw=raw,
            content_blocks=content_blocks,
        )
