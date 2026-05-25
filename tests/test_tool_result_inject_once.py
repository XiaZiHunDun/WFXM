"""PR3: inject_once spill — full pointer once, compact ref on later API rounds."""

from __future__ import annotations

from butler.config import reload_butler_settings
from butler.core.tool_result_storage import (
    INJECT_ONCE_REF_TAG,
    PERSISTED_OUTPUT_TAG,
    apply_inject_once_policy,
    build_spill_message,
    is_inject_once_ref,
    maybe_spill_tool_result,
    persist_tool_result_text,
    reset_inject_once_state,
)
from butler.execution_context import use_execution_context


def test_maybe_spill_registers_inject_once_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL", "1")
    monkeypatch.setenv("BUTLER_TOOL_RESULT_INJECT_ONCE", "1")
    monkeypatch.setenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "50")
    reset_inject_once_state()

    body = "web-fetch-body\n" * 30
    with use_execution_context(session_key="sess-inject"):
        out = maybe_spill_tool_result(
            body,
            tool_name="web_fetch",
            tool_use_id="call_wf",
            session_key="sess-inject",
        )

    assert PERSISTED_OUTPUT_TAG in out
    from butler.core.tool_result_storage import get_inject_once_state

    meta = get_inject_once_state("sess-inject").spill_meta.get("call_wf")
    assert meta is not None
    assert meta.tool_name == "web_fetch"
    assert meta.original_size == len(body)


def test_apply_inject_once_first_full_then_compact(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_INJECT_ONCE", "1")
    reset_inject_once_state("sess-2")

    persisted = persist_tool_result_text(
        "line\n" * 100,
        tool_use_id="call_g",
        session_key="sess-2",
    )
    assert persisted is not None
    full = build_spill_message(persisted)
    from butler.core.tool_result_storage import register_spill_inject_meta

    register_spill_inject_meta(
        tool_use_id="call_g",
        session_key="sess-2",
        persisted=persisted,
        tool_name="grep",
    )

    messages = [
        {"role": "assistant", "tool_calls": [{"id": "call_g", "function": {"name": "grep"}}]},
        {"role": "tool", "tool_call_id": "call_g", "content": full},
    ]

    apply_inject_once_policy(messages, session_key="sess-2")
    assert PERSISTED_OUTPUT_TAG in messages[1]["content"]
    assert not is_inject_once_ref(messages[1]["content"])

    apply_inject_once_policy(messages, session_key="sess-2")
    assert is_inject_once_ref(messages[1]["content"])
    assert INJECT_ONCE_REF_TAG in messages[1]["content"]
    assert "inject_once" in messages[1]["content"]
    assert "grep" in messages[1]["content"]
    assert persisted.filepath.as_posix() in messages[1]["content"]


def test_inject_once_disabled_keeps_full_spill(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_INJECT_ONCE", "0")
    reset_inject_once_state("sess-3")

    persisted = persist_tool_result_text("z\n" * 80, tool_use_id="c3", session_key="sess-3")
    full = build_spill_message(persisted)
    messages = [{"role": "tool", "tool_call_id": "c3", "content": full}]

    apply_inject_once_policy(messages, session_key="sess-3")
    apply_inject_once_policy(messages, session_key="sess-3")
    assert PERSISTED_OUTPUT_TAG in messages[0]["content"]
    assert not is_inject_once_ref(messages[0]["content"])


def test_context_pipeline_applies_inject_once(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_TOOL_RESULT_INJECT_ONCE", "1")
    reset_inject_once_state("pipe-sess")

    from butler.core.context_pipeline import ContextPipeline
    from butler.core.loop_types import LoopConfig

    persisted = persist_tool_result_text("a\n" * 60, tool_use_id="c_pipe", session_key="pipe-sess")
    full = build_spill_message(persisted)
    from butler.core.tool_result_storage import register_spill_inject_meta

    register_spill_inject_meta(
        tool_use_id="c_pipe",
        session_key="pipe-sess",
        persisted=persisted,
        tool_name="grep",
    )

    pipeline = ContextPipeline(LoopConfig())
    messages = [{"role": "tool", "tool_call_id": "c_pipe", "content": full}]

    with use_execution_context(session_key="pipe-sess"):
        pipeline.prepare_messages_for_api(messages)
    assert PERSISTED_OUTPUT_TAG in messages[0]["content"]

    with use_execution_context(session_key="pipe-sess"):
        pipeline.prepare_messages_for_api(messages)
    assert is_inject_once_ref(messages[0]["content"])
