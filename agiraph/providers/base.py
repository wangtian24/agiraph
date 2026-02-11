"""Base provider adapter — abstract interface for all LLM providers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from agiraph.models import ModelResponse, ToolDef

logger = logging.getLogger(__name__)


class ProviderAdapter(ABC):
    """Translates between canonical tool defs and provider-specific API formats."""

    @abstractmethod
    def format_tools(self, tools: list[ToolDef]) -> Any:
        """Convert canonical tool defs to provider's API format.
        For native tool-calling models: returns structured schema.
        For text-fallback models: returns None (tools go in prompt instead)."""

    @abstractmethod
    def format_tool_prompt(self, tools: list[ToolDef]) -> str:
        """Generate the tool guidance text for the system prompt.
        For native models: just the guidance (tips, patterns).
        For text models: guidance + full schema + call format instructions."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDef] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """Call the model and return a unified ModelResponse."""

    @abstractmethod
    def count_tokens(self, messages: list[dict]) -> int:
        """Estimate token count for messages."""


class ModelProvider:
    """Unified interface — wraps a ProviderAdapter and handles tool prompt injection."""

    def __init__(self, adapter: ProviderAdapter):
        self.adapter = adapter

    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDef] | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        # Inject tool guidance into system prompt
        if tools and system:
            tool_prompt = self.adapter.format_tool_prompt(tools)
            system = system + "\n\n" + tool_prompt

        return await self.adapter.generate(
            messages=messages,
            tools=tools,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def count_tokens(self, messages: list[dict]) -> int:
        return self.adapter.count_tokens(messages)
