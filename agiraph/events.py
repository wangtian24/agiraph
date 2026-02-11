"""Event system — append-only log with streaming support."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from agiraph.models import Event

logger = logging.getLogger(__name__)


class EventBus:
    """Append-only event log with subscription support."""

    def __init__(self, log_file: Path | None = None):
        self._log_file = log_file
        self._subscribers: list[asyncio.Queue] = []
        self._history: list[Event] = []

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: Event):
        """Emit an event — log and notify subscribers."""
        self._history.append(event)
        self._persist(event)
        self._notify(event)
        logger.debug(f"Event: {event.type} [{event.agent_id}] {event.data}")

    def emit_simple(self, type: str, agent_id: str, **data):
        """Convenience: emit with keyword args."""
        self.emit(Event(type=type, agent_id=agent_id, data=data))

    def recent(self, limit: int = 50, offset: int = 0) -> list[Event]:
        """Get recent events (paginated)."""
        start = max(0, len(self._history) - offset - limit)
        end = len(self._history) - offset
        return self._history[start:end]

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to live events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _persist(self, event: Event):
        if self._log_file:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

    def _notify(self, event: Event):
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
