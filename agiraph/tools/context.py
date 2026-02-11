"""ToolContext — the runtime context passed to every tool implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agiraph.models import Trigger, WorkBoard, WorkNode, Worker, WorkerPool

if TYPE_CHECKING:
    from agiraph.events import EventBus
    from agiraph.message_bus import MessageBus


class ToolContext:
    """Runtime context available to all tool implementations.

    Provides access to the current node, worker, workspace, message bus,
    event bus, and other shared state.
    """

    def __init__(
        self,
        agent_id: str = "",
        agent_path: Path | None = None,
        run_dir: Path | None = None,
        node: WorkNode | None = None,
        worker: Worker | None = None,
        board: WorkBoard | None = None,
        worker_pool: WorkerPool | None = None,
        message_bus: "MessageBus | None" = None,
        event_bus: "EventBus | None" = None,
        human_response_queue: asyncio.Queue | None = None,
        human_timeout: int = 3600,
        trigger_store: list[Trigger] | None = None,
        default_model: str = "anthropic/claude-sonnet-4-5",
    ):
        self.agent_id = agent_id
        self.agent_path = agent_path or Path(".")
        self.run_dir = run_dir
        self.node = node
        self.worker = worker
        self.board = board or WorkBoard()
        self.worker_pool = worker_pool or WorkerPool()
        self.message_bus = message_bus
        self.event_bus = event_bus
        self.human_response_queue = human_response_queue or asyncio.Queue()
        self.human_timeout = human_timeout
        self.trigger_store = trigger_store if trigger_store is not None else []
        self.default_model = default_model

    def resolve_path(self, path: str) -> Path:
        """Resolve a relative path against the run directory."""
        if self.run_dir:
            resolved = (self.run_dir / path).resolve()
            # Security: prevent path traversal outside the agent's home
            if self.agent_path and not str(resolved).startswith(str(self.agent_path.resolve())):
                raise PermissionError(f"Path escapes agent home: {path}")
            return resolved
        return Path(path)

    def emit(self, event_type: str, **data: Any):
        """Emit an event via the event bus."""
        if self.event_bus:
            self.event_bus.emit_simple(event_type, self.agent_id, **data)
