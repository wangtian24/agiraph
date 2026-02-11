"""Tool registry — registers, resolves, and dispatches tool calls."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from agiraph.models import ToolCall, ToolDef

logger = logging.getLogger(__name__)

# Type for tool implementation functions
ToolImpl = Callable[..., Awaitable[str] | str]


class ToolRegistry:
    """Registry of tool definitions and their implementations."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}
        self._impls: dict[str, ToolImpl] = {}

    def register(self, tool_def: ToolDef, impl: ToolImpl):
        """Register a tool definition with its implementation."""
        self._tools[tool_def.name] = tool_def
        self._impls[tool_def.name] = impl

    def get_def(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def get_all(self, include_coordinator: bool = False) -> list[ToolDef]:
        """Get all tool definitions, optionally including coordinator-only tools."""
        return [
            t for t in self._tools.values()
            if include_coordinator or not t.coordinator_only
        ]

    def get_worker_tools(self) -> list[ToolDef]:
        """Get tools available to regular workers."""
        return [t for t in self._tools.values() if not t.coordinator_only]

    def get_coordinator_tools(self) -> list[ToolDef]:
        """Get all tools including coordinator-only."""
        return list(self._tools.values())

    async def dispatch(self, tool_call: ToolCall, context: Any) -> str:
        """Execute a tool call and return the result string."""
        impl = self._impls.get(tool_call.name)
        if not impl:
            return f"Error: Unknown tool '{tool_call.name}'"

        try:
            result = impl(context=context, **tool_call.args)
            # Handle both sync and async implementations
            if hasattr(result, "__await__"):
                result = await result
            return str(result)
        except Exception as e:
            logger.error(f"Tool '{tool_call.name}' failed: {e}", exc_info=True)
            return f"Error executing {tool_call.name}: {e}"

    def names(self) -> list[str]:
        return list(self._tools.keys())
