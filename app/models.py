"""Data models for DAG nodes, plans, and execution state."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    """Status of a DAG node."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Node(BaseModel):
    """A node in the DAG representing a task."""
    id: str
    name: str
    description: str
    provider: str  # openai, anthropic, gemini, minimax
    model: str
    input_contract: Dict[str, Any] = Field(default_factory=dict)
    output_contract: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)  # IDs of prerequisite nodes
    status: NodeStatus = NodeStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None


class Plan(BaseModel):
    """A complete execution plan with DAG structure."""
    plan_id: str
    user_prompt: str
    nodes: List[Node]
    edges: List[Dict[str, str]] = Field(default_factory=list)  # [{"from": "node_id", "to": "node_id"}]
    status: str = "draft"  # draft, approved, executing, completed


class ExecutionState(BaseModel):
    """Current state of plan execution."""
    execution_id: str
    plan_id: str
    node_states: Dict[str, NodeStatus] = Field(default_factory=dict)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    logs: List[str] = Field(default_factory=list)
