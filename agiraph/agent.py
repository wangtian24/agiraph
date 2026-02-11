"""Agent — the top-level entity. One goal, one agent."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from agiraph.config import BASE_DIR, DEFAULT_MODEL
from agiraph.coordinator import Coordinator
from agiraph.events import EventBus
from agiraph.message_bus import MessageBus
from agiraph.models import (
    Trigger, WorkBoard, WorkerPool, generate_id,
)
from agiraph.tools.setup import create_default_registry

logger = logging.getLogger(__name__)


class Agent:
    """Top-level autonomous agent. Give it a goal, it figures out the rest."""

    def __init__(
        self,
        goal: str,
        model: str = DEFAULT_MODEL,
        mode: str = "finite",
        agent_id: str | None = None,
    ):
        self.id = agent_id or generate_id()
        self.goal = goal
        self.coordinator_model = model
        self.mode = mode  # finite | infinite
        self.status = "idle"  # idle | working | waiting_for_human | paused | completed

        # Paths
        self.path = BASE_DIR / self.id
        self.path.mkdir(parents=True, exist_ok=True)

        # Create identity files
        self._init_files()

        # Current run
        self.run_id = generate_id()
        self.current_run_dir = self.path / "runs" / self.run_id
        self.current_run_dir.mkdir(parents=True, exist_ok=True)
        (self.current_run_dir / "nodes").mkdir(exist_ok=True)
        (self.current_run_dir / "workers").mkdir(exist_ok=True)
        (self.current_run_dir / "_messages").mkdir(exist_ok=True)

        # Core systems
        self.board = WorkBoard()
        self.worker_pool = WorkerPool()
        self.message_bus = MessageBus(log_dir=self.current_run_dir / "_messages")
        self.event_bus = EventBus(log_file=self.path / "events.jsonl")
        self.human_response_queue: asyncio.Queue = asyncio.Queue()
        self.triggers: list[Trigger] = []

        # Tool registry
        self.registry = create_default_registry()

        # Conversation log (human-facing)
        self.conversation_log: list[dict] = []

        # Running worker tasks
        self._running_tasks: dict[str, asyncio.Task] = {}

        # Register standard entities on message bus
        self.message_bus.register("coordinator")
        self.message_bus.register("human")

        # Timestamps
        self.created_at = time.time()
        self.updated_at = time.time()

        logger.info(f"Agent {self.id} created: {goal[:80]}")

    def _init_files(self):
        """Create initial identity files if they don't exist."""
        soul = self.path / "SOUL.md"
        if not soul.exists():
            soul.write_text(
                "# Agent\n\n"
                "You are an autonomous AI agent. You work toward your goal with focus and initiative.\n"
            )

        goal_file = self.path / "GOAL.md"
        goal_file.write_text(f"# Goal\n\n{self.goal}\n")

        memory_file = self.path / "MEMORY.md"
        if not memory_file.exists():
            memory_file.write_text("")

        memory_dir = self.path / "memory"
        memory_dir.mkdir(exist_ok=True)
        (memory_dir / "knowledge").mkdir(exist_ok=True)
        (memory_dir / "experiences").mkdir(exist_ok=True)

        index = memory_dir / "index.md"
        if not index.exists():
            index.write_text("# Memory Index\n\n(Empty — will be populated as the agent learns.)\n")

    async def start(self):
        """Start the agent — launches the coordinator loop."""
        coordinator = Coordinator(self)
        await coordinator.run()

    async def send_message(self, message: str, to: str = "coordinator") -> str:
        """Human sends a message to the agent."""
        self.conversation_log.append({
            "role": "human",
            "to": to,
            "content": message,
            "ts": time.time(),
        })
        self.message_bus.send("human", to, message)
        self.updated_at = time.time()
        return f"Message sent to {to}."

    async def respond_to_question(self, response: str):
        """Human responds to an ask_human question."""
        await self.human_response_queue.put(response)
        self.conversation_log.append({
            "role": "human",
            "content": response,
            "ts": time.time(),
        })

    def summary(self) -> dict:
        """Return a summary of the agent's current state."""
        return {
            "id": self.id,
            "goal": self.goal,
            "mode": self.mode,
            "status": self.status,
            "model": self.coordinator_model,
            "node_count": len(self.board.nodes),
            "worker_count": len(self.worker_pool.workers),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def board_view(self) -> dict:
        """Return the work board state."""
        return {
            "nodes": [n.to_dict() for n in self.board.nodes.values()],
            "stages": [
                {
                    "name": s.name,
                    "nodes": s.nodes,
                    "status": s.status,
                }
                for s in self.board.stages
            ],
            "current_stage": self.board.current_stage,
        }

    def workers_view(self) -> list[dict]:
        """Return the worker pool state."""
        return [w.to_dict() for w in self.worker_pool.workers.values()]
