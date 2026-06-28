"""Tests for butler.contracts (P1-D)."""

from __future__ import annotations

from butler.contracts.events import EventsSink
from butler.contracts.sink_registry import get_events_sink, set_events_sink
from butler.gateway.events_sink import register_gateway_events_sink
from butler.gateway.events_sink_impl import GatewayEventsSink


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []
        self.tools: list[tuple[str, str, str, str]] = []

    def record_generic_event(self, session_key: str, event_type: str, data: dict) -> None:
        self.events.append((session_key, event_type, data))

    def record_tool_action(
        self,
        *,
        session_key: str,
        tool_name: str,
        args_preview: str = "",
        source: str = "",
    ) -> None:
        self.tools.append((session_key, tool_name, args_preview, source))


def test_events_sink_protocol_shape():
    sink: EventsSink = _RecordingSink()
    sink.record_generic_event("sk", "ping", {"ok": True})
    sink.record_tool_action(session_key="sk", tool_name="read_file", source="loop")
    assert isinstance(sink, EventsSink)


def test_sink_registry_roundtrip():
    rec = _RecordingSink()
    set_events_sink(rec)
    try:
        assert get_events_sink() is rec
    finally:
        set_events_sink(None)


def test_register_gateway_events_sink():
    set_events_sink(None)
    register_gateway_events_sink()
    try:
        sink = get_events_sink()
        assert isinstance(sink, GatewayEventsSink)
        sink.record_generic_event("sk", "ping", {"ok": True})
        sink.record_tool_action(session_key="sk", tool_name="read_file", source="loop")
    finally:
        set_events_sink(None)


def test_gateway_sink_satisfies_contracts_protocol():
    from butler.gateway.events_sink_impl import install_gateway_events_sink

    sink = install_gateway_events_sink()
    assert isinstance(sink, EventsSink)


def test_gateway_sink_delegates_transcript_writes(monkeypatch):
    generic: list[tuple[str, str, dict]] = []
    tools: list[tuple[str, str, str, str]] = []

    def _record_generic(session_key: str, event_type: str, data: dict) -> None:
        generic.append((session_key, event_type, data))

    def _record_tool(
        session_key: str,
        *,
        tool_name: str,
        args_preview: str = "",
        source: str = "",
    ) -> None:
        tools.append((session_key, tool_name, args_preview, source))

    monkeypatch.setattr(
        "butler.core.session_transcript.record_generic_event",
        _record_generic,
    )
    monkeypatch.setattr(
        "butler.core.session_transcript.record_tool_action",
        _record_tool,
    )

    sink = GatewayEventsSink()
    sink.record_generic_event("wechat:u1", "turn_end", {"status": "ok"})
    sink.record_tool_action(
        session_key="wechat:u1",
        tool_name="read_file",
        args_preview='{"path":"x"}',
        source="loop",
    )

    assert generic == [("wechat:u1", "turn_end", {"status": "ok"})]
    assert tools == [("wechat:u1", "read_file", '{"path":"x"}', "loop")]


def test_contracts_registry_gateway_sink_writes(monkeypatch):
    generic: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(
        "butler.core.session_transcript.record_generic_event",
        lambda sk, et, data: generic.append((sk, et, data)),
    )
    set_events_sink(None)
    register_gateway_events_sink()
    try:
        sink = get_events_sink()
        assert sink is not None
        sink.record_generic_event("sk", "workflow_step", {"step": "review"})
        assert generic == [("sk", "workflow_step", {"step": "review"})]
    finally:
        set_events_sink(None)
