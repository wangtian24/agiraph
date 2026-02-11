"""OpenAI (GPT-4, o3) provider adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from agiraph.config import OPENAI_API_KEY
from agiraph.models import ModelResponse, ToolCall, ToolDef, TokenUsage
from agiraph.providers.base import ProviderAdapter

logger = logging.getLogger(__name__)


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
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
        formatted = self._format_messages(messages, system)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = self.format_tools(tools)

        try:
            raw = await self.client.chat.completions.create(**kwargs)
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise

        return self._parse_response(raw)

    def count_tokens(self, messages: list[dict]) -> int:
        total = sum(len(json.dumps(m)) for m in messages)
        return total // 4

    def _format_messages(self, messages: list[dict], system: str | None = None) -> list[dict]:
        formatted = []
        if system:
            formatted.append({"role": "system", "content": system})

        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                formatted.append({"role": "system", "content": msg.get("content", "")})
            elif role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_use_id", msg.get("id", "unknown")),
                    "content": str(msg.get("content", "")),
                })
            elif role == "assistant":
                entry: dict[str, Any] = {"role": "assistant"}
                content = msg.get("content", "")
                if content:
                    entry["content"] = content
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.get("id", "unknown"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": json.dumps(tc.get("args", {})),
                            },
                        }
                        for tc in tool_calls
                    ]
                formatted.append(entry)
            else:
                formatted.append({"role": "user", "content": str(msg.get("content", ""))})
        return formatted

    def _parse_response(self, raw: Any) -> ModelResponse:
        msg = raw.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        name=tc.function.name,
                        args=json.loads(tc.function.arguments),
                        id=tc.id,
                    )
                )
        return ModelResponse(
            text=msg.content,
            tool_calls=tool_calls,
            usage=TokenUsage(raw.usage.prompt_tokens, raw.usage.completion_tokens),
            raw=raw,
        )
