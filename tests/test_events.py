"""Test EventBus."""

from agiraph.events import EventBus
from agiraph.models import Event


def test_emit_and_recent():
    bus = EventBus()
    bus.emit(Event(type="test.event", agent_id="a1", data={"key": "val"}))
    bus.emit(Event(type="test.event2", agent_id="a1", data={"key": "val2"}))

    recent = bus.recent(limit=10)
    assert len(recent) == 2
    assert recent[0].type == "test.event"
    assert recent[1].type == "test.event2"


def test_emit_simple():
    bus = EventBus()
    bus.emit_simple("node.created", "agent1", node_id="n1", task="test")

    recent = bus.recent()
    assert len(recent) == 1
    assert recent[0].data["node_id"] == "n1"


def test_recent_pagination():
    bus = EventBus()
    for i in range(10):
        bus.emit_simple("event", "a1", i=i)

    assert len(bus.recent(limit=3)) == 3
    assert len(bus.recent(limit=100)) == 10
