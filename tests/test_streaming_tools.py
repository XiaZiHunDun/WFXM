"""Streaming read-only tool prefetch (P2)."""

from __future__ import annotations

from butler.core import streaming_tools as st


def test_is_streaming_tool_names():
    assert st.is_streaming_tool("read_file")
    assert st.is_streaming_tool("grep")
    assert st.is_streaming_tool("search_files")
    assert not st.is_streaming_tool("patch")
    assert not st.is_streaming_tool("delegate_task")


def test_try_parse_tool_arguments():
    assert st.try_parse_tool_arguments('{"path": "/tmp/a"}') == {"path": "/tmp/a"}
    assert st.try_parse_tool_arguments("{") is None
    assert st.try_parse_tool_arguments("") is None


def test_notify_dispatches_once(monkeypatch):
    monkeypatch.setenv("BUTLER_STREAMING_TOOLS", "1")
    calls: list[tuple] = []

    def cb(idx: int, tool_id: str, name: str, args: dict) -> None:
        calls.append((idx, tool_id, name, args))

    collected = {
        0: {
            "id": "call_abc",
            "name": "read_file",
            "arguments": '{"path": "README.md"}',
        }
    }
    st.notify_complete_tool_calls_from_stream(collected, cb)
    assert len(calls) == 1
    assert calls[0][1] == "call_abc"
    assert calls[0][3]["path"] == "README.md"

    st.notify_complete_tool_calls_from_stream(collected, cb)
    assert len(calls) == 1


def test_batch_eligible_all_read_only(monkeypatch):
    monkeypatch.setenv("BUTLER_STREAMING_TOOLS", "1")

    class TC:
        def __init__(self, name: str):
            self.name = name

    assert st.batch_eligible_for_streaming([TC("read_file"), TC("grep")])
    assert not st.batch_eligible_for_streaming([TC("read_file"), TC("patch")])
