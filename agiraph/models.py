"""Core data structures for Agiraph v2-A."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Tool System
# ---------------------------------------------------------------------------


@dataclass
class ToolDef:
    """Canonical tool definition. Adapters translate this to provider-specific formats."""

    name: str
    description: str  # short, for the schema
    parameters: dict[str, Any]  # JSON Schema
    guidance: str = ""  # long, for the prompt (tips, patterns)
    coordinator_only: bool = False


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str = field(default_factory=lambda: f"tc_{uuid.uuid4().hex[:8]}")


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ModelResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: Any = None
    content_blocks: list[dict] | None = None  # Raw API content blocks for multi-turn (web search)


# ---------------------------------------------------------------------------
# Work System
# ---------------------------------------------------------------------------


@dataclass
class StageContract:
    max_iterations_per_node: int = 20
    timeout_seconds: int = 600
    checkpoint_policy: str = "all_must_complete"  # all_must_complete | majority | any


@dataclass
class Stage:
    name: str
    nodes: list[str] = field(default_factory=list)
    contract: StageContract = field(default_factory=StageContract)
    status: str = "planning"  # planning | running | reconvening | completed


@dataclass
class WorkNode:
    """A unit of work with its own folder of truth."""

    id: str = field(default_factory=generate_id)
    task: str = ""
    dependencies: list[str] = field(default_factory=list)
    refs: dict[str, str] = field(default_factory=dict)
    status: str = "pending"  # pending | assigned | running | completed | failed
    assigned_worker: str | None = None
    parent_node: str | None = None
    children: list[str] = field(default_factory=list)
    data_dir: Path | None = None
    result: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "dependencies": self.dependencies,
            "refs": self.refs,
            "status": self.status,
            "assigned_worker": self.assigned_worker,
            "parent_node": self.parent_node,
            "children": self.children,
            "data_dir": str(self.data_dir) if self.data_dir else None,
            "result": self.result[:200] if self.result else None,
            "created_at": self.created_at,
        }


@dataclass
class WorkBoard:
    nodes: dict[str, WorkNode] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)
    current_stage: int = 0

    def add(self, node: WorkNode):
        self.nodes[node.id] = node

    def get(self, node_id: str) -> WorkNode | None:
        return self.nodes.get(node_id)

    def ready_nodes(self) -> list[WorkNode]:
        """Nodes that are pending and have all dependencies met."""
        ready = []
        for n in self.nodes.values():
            if n.status != "pending":
                continue
            deps_met = all(
                self.nodes.get(d) and self.nodes[d].status == "completed" for d in n.dependencies
            )
            if deps_met:
                ready.append(n)
        return ready


@dataclass
class Worker:
    """An executor with its own memory and identity."""

    id: str = field(default_factory=generate_id)
    name: str = ""
    role: str = "Generalist"  # Coordinator, Researcher, Analyzer, Programmer, Generalist, etc.
    type: str = "harnessed"  # harnessed | autonomous | claude_code
    model: str | None = None
    agent_command: str | None = None
    status: str = "idle"  # idle | busy | waiting_for_human | stopped
    capabilities: list[str] = field(default_factory=list)
    worker_dir: Path | None = None
    max_iterations: int = 20

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "type": self.type,
            "model": self.model,
            "status": self.status,
            "capabilities": self.capabilities,
        }


@dataclass
class WorkerPool:
    workers: dict[str, Worker] = field(default_factory=dict)
    max_concurrent: int = 4

    def idle_workers(self) -> list[Worker]:
        return [w for w in self.workers.values() if w.status == "idle"]

    def add(self, worker: Worker):
        self.workers[worker.id] = worker

    def get(self, worker_id: str) -> Worker | None:
        return self.workers.get(worker_id)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@dataclass
class Message:
    from_id: str
    to_id: str
    content: str
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"from_id": self.from_id, "to_id": self.to_id, "content": self.content, "ts": self.ts}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@dataclass
class Event:
    type: str
    agent_id: str
    ts: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "agent_id": self.agent_id, "ts": self.ts, "data": self.data}


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


@dataclass
class TriggerAction:
    type: str  # wake_agent | run_node | send_message
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trigger:
    id: str = field(default_factory=generate_id)
    agent_id: str = ""
    type: str = "delayed"  # delayed | at_time | scheduled | heartbeat | on_event | on_idle
    action: TriggerAction = field(default_factory=lambda: TriggerAction(type="wake_agent"))
    status: str = "active"  # active | paused | expired | fired
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "type": self.type,
            "action": {"type": self.action.type, "payload": self.action.payload},
            "status": self.status,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
