"""Tool result spill-to-disk (P0-1)."""

from __future__ import annotations

from butler.config import reload_butler_settings
from butler.core import context_compressor
from butler.core.tool_result_storage import (
    PERSISTED_OUTPUT_TAG,
    build_spill_message,
    is_persisted_tool_result,
    maybe_spill_tool_result,
    persist_tool_result_text,
    tool_result_path,
    tool_results_dir,
)
from butler.execution_context import use_execution_context


def test_maybe_spill_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "1000")
    small = "x" * 500
    assert maybe_spill_tool_result(small, tool_use_id="call_1", session_key="sess-a") == small


def test_maybe_spill_writes_file_and_pointer(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "100")
    body = "line\n" * 200
    out = maybe_spill_tool_result(
        body,
        tool_name="grep",
        tool_use_id="call_big",
        session_key="wx-user-1",
    )
    assert PERSISTED_OUTPUT_TAG in out
    assert is_persisted_tool_result(out)
    path = tool_result_path("wx-user-1", "call_big")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == body
    assert "read_file" not in out or "完整结果" in out


def test_spill_disabled_returns_original(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL", "0")
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "10")
    body = "y" * 500
    assert maybe_spill_tool_result(body, tool_use_id="c1", session_key="s") == body


def test_persist_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    text = "z" * 50
    r1 = persist_tool_result_text(text, tool_use_id="idem", session_key="s1")
    r2 = persist_tool_result_text(text, tool_use_id="idem", session_key="s1")
    assert r1 is not None and r2 is not None
    assert r1.filepath == r2.filepath
    assert tool_results_dir("s1").glob("*.txt")


def test_prune_skips_persisted_output():
    pointer = (
        f"{PERSISTED_OUTPUT_TAG}\n输出过大（9000 字符）。"
        "完整结果已保存至：/tmp/x.txt\n\n预览：\nhi\n</persisted-output>"
    )
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "content": pointer},
        {"role": "tool", "content": "x" * 5000},
    ]
    out = context_compressor.prune_tool_outputs(messages)
    assert out[1]["content"] == pointer
    assert "[Tool output pruned" in out[2]["content"]


def test_tool_batch_spills_on_append(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL", "1")
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "200")

    from butler.core.loop_types import LoopCallbacks, LoopConfig
    from butler.core.tool_batch import process_tool_calls
    from butler.transport.types import NormalizedResponse, ToolCall

    huge = "output-" * 40

    def _dispatch(_name: str, _args: dict) -> str:
        return huge

    response = NormalizedResponse(
        content="",
        tool_calls=[ToolCall(id="call_spill", name="grep", arguments="{}")],
    )
    messages: list[dict] = []
    with use_execution_context(session_key="batch-sess"):
        process_tool_calls(
            response=response,
            messages=messages,
            config=LoopConfig(enable_parallel_tools=False),
            callbacks=LoopCallbacks(),
            guardrails=None,
            dispatch_tool=_dispatch,
            interrupt_check=lambda: False,
        )

    tool_msg = [m for m in messages if m.get("role") == "tool"][0]
    assert PERSISTED_OUTPUT_TAG in tool_msg["content"]
    assert tool_result_path("batch-sess", "call_spill").is_file()


def test_session_tool_result_path_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    from butler.core.tool_result_storage import (
        is_readable_session_tool_result_path,
        persist_tool_result_text,
        tool_result_path,
    )
    from butler.execution_context import use_execution_context
    from butler.tools.path_safety import check_tool_path

    sk = "wechat:test-session"
    body = "scrape body\nline2\n"
    persisted = persist_tool_result_text(body, tool_use_id="call_abc", session_key=sk)
    assert persisted is not None
    path = tool_result_path(sk, "call_abc")

    with use_execution_context(session_key=sk):
        assert is_readable_session_tool_result_path(str(path))
        safety = check_tool_path(str(path), for_write=False)
        assert safety.allowed, safety.error
