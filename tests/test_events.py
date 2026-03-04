import logging
from tapes.events.bus import EventBus


def test_listener_called():
    bus = EventBus()
    calls = []
    bus.on("test_event", lambda x: calls.append(x))
    bus.emit("test_event", x=42)
    assert calls == [42]


def test_buggy_listener_does_not_propagate(caplog):
    bus = EventBus()
    second_called = []
    bus.on("event", lambda: 1 / 0)
    bus.on("event", lambda: second_called.append(True))
    with caplog.at_level(logging.ERROR):
        bus.emit("event")
    assert "ZeroDivisionError" in caplog.text
    assert second_called  # second listener still ran


def test_no_listeners_is_noop():
    bus = EventBus()
    bus.emit("no_listeners")  # must not raise
