"""Thread-safe message bus for inter-node communication."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from pathlib import Path

from agiraph.models import Message

logger = logging.getLogger(__name__)


class MessageBus:
    """Queue-based messaging between workers, coordinator, and human."""

    def __init__(self, log_dir: Path | None = None):
        self._queues: dict[str, list[Message]] = defaultdict(list)
        self._lock = threading.Lock()
        self._log_dir = log_dir
        self._subscribers: list[asyncio.Queue] = []

        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)

    def send(self, from_id: str, to_id: str, content: str) -> Message:
        """Send a message from one entity to another."""
        msg = Message(from_id=from_id, to_id=to_id, content=content)
        with self._lock:
            self._queues[to_id].append(msg)
        self._log(msg)
        self._notify(msg)
        logger.debug(f"Message: {from_id} → {to_id}: {content[:80]}")
        return msg

    def broadcast(self, from_id: str, content: str, exclude: set[str] | None = None):
        """Send a message to all entities."""
        exclude = exclude or set()
        with self._lock:
            recipients = [k for k in self._queues.keys() if k not in exclude and k != from_id]
        for recipient in recipients:
            self.send(from_id, recipient, content)

    def receive(self, entity_id: str) -> list[Message]:
        """Drain and return all messages for an entity."""
        with self._lock:
            messages = self._queues.pop(entity_id, [])
        return messages

    def peek(self, entity_id: str) -> list[Message]:
        """Peek at messages without draining."""
        with self._lock:
            return list(self._queues.get(entity_id, []))

    def has_messages(self, entity_id: str) -> bool:
        with self._lock:
            return bool(self._queues.get(entity_id))

    def register(self, entity_id: str):
        """Register an entity so broadcasts reach it."""
        with self._lock:
            if entity_id not in self._queues:
                self._queues[entity_id] = []

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to all messages (for event streaming)."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _log(self, msg: Message):
        if self._log_dir:
            log_file = self._log_dir / "messages.jsonl"
            with open(log_file, "a") as f:
                f.write(json.dumps(msg.to_dict()) + "\n")

    def _notify(self, msg: Message):
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
