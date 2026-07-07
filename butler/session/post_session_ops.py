"""Post-session extraction, watermark tracking, and turn buffering."""

from __future__ import annotations

from butler.env_parse import int_env
import asyncio
import logging
import threading
from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.session.post_session_guard import guard_post_session

logger = logging.getLogger(__name__)

from butler.session.lifecycle import (
    _POST_SESSION_LOCK,
    _POST_SESSION_MIN_CONV_MESSAGES,
)


def post_session_buffer_threshold() -> int:
    """Max buffered user+assistant messages before incremental post_session."""
    import os

    try:
        return cast(int, int_env("BUTLER_POST_SESSION_BUFFER_MESSAGES", 8, min=4))
    except ValueError:
        return 8


def _conversation_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
            out.append(msg)
    return out


def _turn_pairs_in_messages(messages: list[Any]) -> int:
    return len(_conversation_messages(messages)) // 2


def _watermark_store(orchestrator: Any) -> dict[str, int]:
    store = getattr(orchestrator, "_post_session_pairs_extracted", None)
    if not isinstance(store, dict):
        store = {}
        orchestrator._post_session_pairs_extracted = store
    return store


def _watermark_key(session_id: str) -> str:
    return str(session_id or "").strip() or "_default"


def get_post_session_pairs_extracted(orchestrator: Any, session_id: str = "") -> int:
    return int(_watermark_store(orchestrator).get(_watermark_key(session_id), 0))


def reset_post_session_watermark(orchestrator: Any, session_id: str = "") -> None:
    _watermark_store(orchestrator).pop(_watermark_key(session_id), None)


def _increment_post_session_watermark(
    orchestrator: Any, session_id: str, messages: list[Any]
) -> None:
    pairs = _turn_pairs_in_messages(messages)
    if pairs <= 0:
        return
    key = _watermark_key(session_id)
    store = _watermark_store(orchestrator)
    store[key] = int(store.get(key, 0)) + pairs


def _ensure_turn_buffer(provider: Any) -> list[dict[str, Any]]:
    buf = getattr(provider, "_turn_buffer", None)
    if not isinstance(buf, list):
        buf = []
        provider._turn_buffer = buf
    return buf


def drain_post_session_buffer(provider: Any) -> list[dict[str, Any]]:
    buf = _ensure_turn_buffer(provider)
    drained = list(buf)
    buf.clear()
    return drained


def _execute_post_session(orchestrator: Any, messages: list[Any]) -> dict[str, Any]:
    from butler.session.post_session import PostSessionProcessor
    from butler.transport.auxiliary_client import auxiliary_llm_call_factory

    processor = PostSessionProcessor()
    processor.set_llm_call(auxiliary_llm_call_factory("post_session"))
    project_name = ""
    pm = getattr(orchestrator, "project_manager", None)
    if pm is not None:
        project_name = str(getattr(pm, "current_project", "") or "")

    return asyncio.run(
        processor.process(
            messages=messages,
            butler_memory=orchestrator.butler_memory,
            project_memory=getattr(orchestrator, "_project_memory", None),
            skill_manager=getattr(orchestrator, "_skill_manager", None),
            project_name=project_name,
        )
    )


def _run_post_session_locked(
    orchestrator: Any,
    conv: list[dict[str, Any]],
    *,
    session_id: str,
    advance_watermark: bool,
) -> dict[str, Any]:
    result = _execute_post_session(orchestrator, conv)
    if advance_watermark and not result.get("skipped"):
        _increment_post_session_watermark(orchestrator, session_id, conv)
    if result.get("memory_updates") or result.get("skills_extracted"):
        logger.info(
            "Post-session extract session=%s memory=%s skills=%s",
            session_id or "-",
            result.get("memory_updates", 0),
            result.get("skills_extracted", 0),
        )
    if not result.get("skipped"):
        safe_best_effort(
            lambda: __import__(
                "butler.core.post_commit", fromlist=["flush_after_commit"]
            ).flush_after_commit(),
            label="post_session.flush_after_commit",
            default=None,
        )
    return result


def _resolve_session_key_for_end() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    return safe_best_effort(
        _run,
        label="post_session.session_key",
        default="",
    ) or ""


def _run_session_end_hooks(session_key: str, *, reason: str) -> None:
    def _run() -> None:
        from butler.hooks.runner import run_session_end_hooks

        run_session_end_hooks(reason=reason, session_key=session_key)

    safe_best_effort(_run, label="post_session.session_end_hooks", default=None)


def _write_session_summary_snapshot_safe(
    orchestrator: Any,
    agent_loop: Any,
    *,
    extract_result: dict[str, Any],
    session_id: str,
) -> None:
    def _run() -> None:
        from butler.session.new_session import write_session_summary_snapshot

        write_session_summary_snapshot(
            orchestrator,
            agent_loop,
            extract_result=extract_result,
            session_id=session_id,
        )

    safe_best_effort(_run, label="post_session.summary_snapshot", default=None)


def run_post_session_extraction(
    orchestrator: Any,
    messages: list[Any],
    *,
    background: bool = False,
    session_id: str = "",
    advance_watermark: bool = True,
) -> dict[str, Any]:
    """Single post_session entry (mutex, orchestrator-owned memory/skills)."""
    conv = _conversation_messages(messages)
    if len(conv) < _POST_SESSION_MIN_CONV_MESSAGES:
        return {"skipped": True, "reason": "short_history"}

    def _run() -> dict[str, Any]:
        with _POST_SESSION_LOCK:
            result = guard_post_session(
                lambda: _run_post_session_locked(
                    orchestrator,
                    conv,
                    session_id=session_id,
                    advance_watermark=advance_watermark,
                )
            )
            return result if isinstance(result, dict) else {"error": "post_session_guard_failed"}

    if background:
        threading.Thread(target=_run, daemon=True).start()
        return {"scheduled": True, "background": True}
    return _run()


def record_post_session_turn(
    orchestrator: Any,
    provider: Any,
    user_content: str,
    assistant_content: str,
    *,
    session_id: str = "",
) -> None:
    """Buffer a turn; flush incremental post_session when threshold reached."""
    if not user_content and not assistant_content:
        return
    buf = _ensure_turn_buffer(provider)
    buf.append({"role": "user", "content": user_content})
    buf.append({"role": "assistant", "content": assistant_content})
    if len(buf) >= post_session_buffer_threshold():
        batch = drain_post_session_buffer(provider)
        run_post_session_extraction(
            orchestrator,
            batch,
            background=True,
            session_id=session_id,
        )


def _unextracted_conversation_messages(
    orchestrator: Any,
    loop_messages: list[Any],
    *,
    session_id: str = "",
    pending_tail: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    conv = _conversation_messages(loop_messages)
    start = get_post_session_pairs_extracted(orchestrator, session_id) * 2
    slice_msgs = conv[start:] if start < len(conv) else []
    if pending_tail:
        tail = _conversation_messages(pending_tail)
        if tail and (not slice_msgs or tail != slice_msgs[-len(tail) :]):
            slice_msgs = slice_msgs + tail
    return slice_msgs


def trigger_session_end(
    orchestrator: Any,
    agent_loop: Any | None,
    *,
    session_id: str = "",
    reason: str = "end",
) -> dict[str, Any]:
    """Run post-session on turns not yet covered by incremental extraction."""
    session_key = str(session_id or "").strip() or _resolve_session_key_for_end()
    _run_session_end_hooks(session_key, reason=reason)

    result = guard_post_session(
        lambda: _trigger_session_end_body(
            orchestrator,
            agent_loop,
            session_id=session_id,
            session_key=session_key,
        )
    )
    return result if isinstance(result, dict) else {"error": "post_session_guard_failed"}


def _trigger_session_end_body(
    orchestrator: Any,
    agent_loop: Any,
    *,
    session_id: str,
    session_key: str,
) -> dict[str, Any]:
    if not agent_loop or not hasattr(agent_loop, "messages"):
        return {"skipped": True, "reason": "no_agent_loop"}

    provider = getattr(orchestrator, "memory_provider", None)
    pending_tail = drain_post_session_buffer(provider) if provider is not None else []

    to_process = _unextracted_conversation_messages(
        orchestrator,
        list(agent_loop.messages),
        session_id=session_id,
        pending_tail=pending_tail,
    )
    if len(to_process) < _POST_SESSION_MIN_CONV_MESSAGES:
        reset_post_session_watermark(orchestrator, session_id)
        return {"skipped": True, "reason": "short_history"}

    result = run_post_session_extraction(
        orchestrator,
        to_process,
        background=False,
        session_id=session_id,
        advance_watermark=False,
    )
    reset_post_session_watermark(orchestrator, session_id)
    _write_session_summary_snapshot_safe(
        orchestrator,
        agent_loop,
        extract_result=result,
        session_id=session_key,
    )
    return result
