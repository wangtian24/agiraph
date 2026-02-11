"""Test core data structures."""

from agiraph.models import (
    WorkNode, WorkBoard, Worker, WorkerPool, Message, Event,
    ToolDef, ToolCall, Stage, StageContract, generate_id,
)


def test_generate_id():
    id1 = generate_id()
    id2 = generate_id()
    assert len(id1) == 12
    assert id1 != id2


def test_work_node_defaults():
    node = WorkNode(task="test task")
    assert node.status == "pending"
    assert node.assigned_worker is None
    assert node.children == []
    assert node.id  # auto-generated


def test_work_board():
    board = WorkBoard()
    n1 = WorkNode(id="a", task="first")
    n2 = WorkNode(id="b", task="second", dependencies=["a"])
    board.add(n1)
    board.add(n2)

    assert board.get("a") is n1
    assert board.get("b") is n2
    assert board.get("c") is None

    # Only n1 should be ready (n2 depends on a)
    ready = board.ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "a"

    # Complete n1, now n2 should be ready
    n1.status = "completed"
    ready = board.ready_nodes()
    assert len(ready) == 1
    assert ready[0].id == "b"


def test_worker_pool():
    pool = WorkerPool()
    w1 = Worker(id="w1", name="Alice", status="idle")
    w2 = Worker(id="w2", name="Bob", status="busy")
    pool.add(w1)
    pool.add(w2)

    assert len(pool.idle_workers()) == 1
    assert pool.idle_workers()[0].name == "Alice"


def test_tool_def():
    tool = ToolDef(
        name="test",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        guidance="Use wisely.",
    )
    assert tool.name == "test"
    assert not tool.coordinator_only


def test_work_node_to_dict():
    node = WorkNode(id="abc", task="do something", status="running")
    d = node.to_dict()
    assert d["id"] == "abc"
    assert d["task"] == "do something"
    assert d["status"] == "running"


def test_message():
    msg = Message(from_id="alice", to_id="bob", content="hello")
    d = msg.to_dict()
    assert d["from_id"] == "alice"
    assert d["to_id"] == "bob"
    assert d["content"] == "hello"
    assert "ts" in d


def test_event():
    event = Event(type="node.created", agent_id="agent1", data={"node_id": "n1"})
    d = event.to_dict()
    assert d["type"] == "node.created"
    assert d["data"]["node_id"] == "n1"
