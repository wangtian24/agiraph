"""Test MessageBus."""

from agiraph.message_bus import MessageBus


def test_send_and_receive():
    bus = MessageBus()
    bus.register("alice")
    bus.register("bob")

    bus.send("alice", "bob", "hello bob")
    bus.send("alice", "bob", "second message")

    msgs = bus.receive("bob")
    assert len(msgs) == 2
    assert msgs[0].content == "hello bob"
    assert msgs[1].content == "second message"

    # Should be drained
    assert bus.receive("bob") == []


def test_peek():
    bus = MessageBus()
    bus.register("alice")
    bus.send("bob", "alice", "hello")

    assert len(bus.peek("alice")) == 1
    assert len(bus.peek("alice")) == 1  # still there
    assert len(bus.receive("alice")) == 1  # now drained
    assert len(bus.peek("alice")) == 0


def test_broadcast():
    bus = MessageBus()
    bus.register("alice")
    bus.register("bob")
    bus.register("carol")

    bus.broadcast("alice", "everyone listen")

    assert len(bus.receive("bob")) == 1
    assert len(bus.receive("carol")) == 1
    assert len(bus.receive("alice")) == 0  # sender doesn't get own broadcast


def test_has_messages():
    bus = MessageBus()
    bus.register("alice")
    assert not bus.has_messages("alice")
    bus.send("bob", "alice", "hey")
    assert bus.has_messages("alice")
