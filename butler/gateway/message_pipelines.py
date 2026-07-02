"""R1-6 inbound pipeline phases for ``ButlerMessageHandler.handle_message``.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-6

The original ``handle_message`` (243-617, ~334 non-blank lines) was a
god method that mixed session resolution, text transformation, guard
checks (io_guardrail, human_gate, injection_guard, injection_llm,
bot_loop_guard, two_phase_confirm), pre-dispatch rewrites,
idempotency, session initializing, queue dispatch, and reply
admission — all in one linear flow with no test seams.

This module exposes the **pre-session** pipeline as composable phase
functions. Each takes the handler instance plus the per-turn state it
needs and returns either:

* ``None``  — pipeline should continue to the next phase
* ``str``   — terminal user-facing reply (early return)

Post-condition: every phase helper is a thin orchestrator under 50
source lines (R1-5.2 size contract — see
``tests/test_message_handler_split.py``).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


def _record_injection_transcript(
    session_key: str,
    entry_type: str,
    score: float,
    text: str,
    *,
    label: str,
) -> None:
    from butler.core.best_effort import safe_best_effort

    def _run() -> None:
        from butler.core.session_transcript import append_transcript_entry

        append_transcript_entry(
            session_key,
            entry_type,
            {"score": score, "preview": text[:120]},
        )

    safe_best_effort(_run, label=label, default=None)


def _warm_session_skills(orchestrator: Any) -> None:
    from butler.core.best_effort import safe_best_effort

    def _jieba() -> None:
        from butler.skills.similarity import _ensure_jieba

        _ensure_jieba()

    safe_best_effort(_jieba, label="message_pipelines.jieba_warmup", default=None)
    mgr = getattr(orchestrator, "_skill_manager", None)
    if mgr is not None:
        mgr.list_skills()


# ---------------------------------------------------------------------------
# Phase 1 — resolve the canonical ``platform:chat_id:project`` session key.
# ---------------------------------------------------------------------------

def _phase_resolve_session_key(
    handler: "ButlerMessageHandler",
    *,
    platform: str,
    external_id: str | None,
    session_key: str | None,
) -> str:
    """Phase: normalize inbound args to a canonical session key."""
    return handler.resolve_session_key(
        platform=platform,
        external_id=external_id,
        session_key=session_key,
    )


# ---------------------------------------------------------------------------
# Phase 2 — apply platform-specific text transformation (message_ir).
# ---------------------------------------------------------------------------

def _phase_transform_inbound_text(
    text: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    """Phase: delegate to ``message_ir.inbound_text_from_gateway``.

    Wrapped in try/except to preserve the original fail-open behavior:
    if the transformer is missing or raises, the raw text is used.
    """
    from butler.core.best_effort import safe_best_effort

    def _run() -> str:
        from butler.core.message_ir import inbound_text_from_gateway

        return inbound_text_from_gateway(
            text,
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )

    transformed = safe_best_effort(
        _run,
        label="message_pipelines.inbound_text_transform",
        default=None,
    )
    return transformed if transformed is not None else text


# ---------------------------------------------------------------------------
# Phase 3 — select the MCP profile for the session based on the text.
# ---------------------------------------------------------------------------

def _phase_apply_mcp_profile(text: str, session_key: str) -> None:
    """Phase: select and bind the MCP profile for this session."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> None:
        from butler.mcp.profiles import (
            mcp_profiles_enabled,
            select_profile_for_text,
            set_session_profile,
        )

        if mcp_profiles_enabled() and text.strip():
            set_session_profile(session_key, select_profile_for_text(text))

    safe_best_effort(_run, label="message_pipelines.mcp_profile", default=None)


# ---------------------------------------------------------------------------
# Phase 4 — io guardrail (fail-closed on exception).
# ---------------------------------------------------------------------------

def _phase_apply_io_guardrail(text: str) -> Optional[str]:
    """Phase: io guardrail tripwire. Returns a blocking reply or None."""
    try:
        from butler.core.io_guardrail import check_inbound_text, io_guardrail_enabled

        if io_guardrail_enabled():
            guard = check_inbound_text(text)
            if guard.tripwire and not guard.allowed:
                return guard.user_message or "消息未通过入站安全检查。"
    except ImportError as exc:
        logger.info("io_guardrail module not available: %s", exc)
    except Exception as exc:
        logger.error("io_guardrail check raised — fail-closed: %s", exc)
        return "安全检查模块异常，消息已拦截。请稍后重试。"
    return None


# ---------------------------------------------------------------------------
# Phase 5 — human gate (with owner check on gate reply).
# ---------------------------------------------------------------------------

def _phase_apply_human_gate(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
) -> Optional[str]:
    """Phase: human gate — blocks (with owner check) if pending review."""
    try:
        from butler.human_gate import resolve_human_gate_message

        from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

        is_owner = is_gateway_owner(platform=platform, external_id=external_id)
        gate_reply = resolve_human_gate_message(
            session_key, text, owner_verified=is_owner,
        )
        if gate_reply is not None:
            return gate_reply
    except ImportError as exc:
        logger.info("human_gate module not available: %s", exc)
    except Exception as exc:
        logger.error("human_gate check raised — fail-closed: %s", exc)
        return "审批门控模块异常，消息已拦截。请稍后重试。"
    return None


# ---------------------------------------------------------------------------
# Phase 6 — injection risk scoring (heuristic).
# ---------------------------------------------------------------------------

def _phase_apply_injection_guard(
    text: str, session_key: str,
) -> tuple[str, Optional[str]]:
    """Phase: heuristic injection scoring + adversarial marker rewrite.

    Returns ``(new_text, block_or_None)``. When ``block`` is set,
    the caller must short-circuit and return it as the final reply
    (fail-closed semantics from the original ``handle_message``).
    """
    try:
        from butler.memory.injection_guard import (
            injection_score_enabled,
            mark_adversarial_user_text,
            score_injection_risk,
        )

        if injection_score_enabled():
            risk = score_injection_risk(text)
            if risk > 0:
                _record_injection_transcript(
                    session_key,
                    "injection_score",
                    risk,
                    text,
                    label="message_pipelines.injection_score_transcript",
                )
        return mark_adversarial_user_text(text), None
    except ImportError as exc:
        logger.info("injection_guard module not available: %s", exc)
        return text, None
    except Exception as exc:
        logger.error("injection_guard raised — fail-closed: %s", exc)
        return text, "注入检测模块异常，消息已拦截。请稍后重试。"


# ---------------------------------------------------------------------------
# Phase 7 — LLM-based injection gate (with bypass/pending handling).
# ---------------------------------------------------------------------------

def _phase_apply_injection_llm(text: str, session_key: str) -> Optional[str]:
    """Phase: LLM-driven injection gate. Returns a blocking reply or None."""
    try:
        from butler.human_gate import (
            consume_injection_bypass,
            format_pending_hint,
            has_injection_review_pending,
            request_injection_review_gate,
        )
        from butler.memory.injection_llm_score import (
            injection_llm_gate_enabled,
            injection_llm_score_enabled,
            should_block_inbound_llm_score,
        )

        if not injection_llm_score_enabled():
            return None
        if consume_injection_bypass(session_key):
            return None
        if has_injection_review_pending(session_key):
            hint = format_pending_hint(session_key)
            if hint:
                return hint
            return None
        blocked, llm_score, block_msg = should_block_inbound_llm_score(text)
        if llm_score is not None:
            _record_injection_transcript(
                session_key,
                "injection_llm_score",
                llm_score,
                text,
                label="message_pipelines.injection_llm_transcript",
            )
        if not blocked:
            return None
        if injection_llm_gate_enabled() and llm_score is not None:
            request_injection_review_gate(session_key, score=llm_score)
            return format_pending_hint(session_key) or block_msg
        return block_msg
    except ImportError as exc:
        logger.info("injection_llm_score module not available: %s", exc)
        return None
    except Exception as exc:
        logger.error("injection_llm_score raised — fail-closed: %s", exc)
        return "LLM 注入检测模块异常，消息已拦截。请稍后重试。"


# ---------------------------------------------------------------------------
# Phase 8 — bot loop guard (group chat echo loop prevention).
# ---------------------------------------------------------------------------

def _phase_apply_bot_loop_guard(
    text: str,
    session_key: str,
    *,
    external_id: str | None,
) -> Optional[str]:
    """Phase: suppress group-chat bot echo loops."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> Optional[str]:
        from butler.gateway.bot_loop_guard import record_and_should_suppress

        chat_id = session_key.split(":")[-1] if ":" in session_key else session_key
        suppress, _reason = record_and_should_suppress(
            chat_id=chat_id,
            sender_id=str(external_id or ""),
            text=text,
        )
        if suppress:
            return "（已忽略：群聊 bot 互回复环防护）"
        return None

    return safe_best_effort(_run, label="message_pipelines.bot_loop_guard", default=None)


# ---------------------------------------------------------------------------
# Phase 9 — two-phase confirm (with owner check on confirm reply).
# ---------------------------------------------------------------------------

def _phase_apply_two_phase_confirm(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
) -> Optional[str]:
    """Phase: dispatch / confirm / cancel two-phase confirm flow."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> Optional[str]:
        from butler.core.two_phase_confirm import (
            cancel_pending_unless_confirm,
            try_execute_pending_confirm,
        )

        pending_reply = try_execute_pending_confirm(text, session_key=session_key)
        if pending_reply is not None:
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

            if not is_gateway_owner(platform=platform, external_id=external_id):
                return owner_required_message()
            return pending_reply
        cancel_note = cancel_pending_unless_confirm(text, session_key=session_key)
        if cancel_note:
            return f"{cancel_note}\n\n{text}"
        return None

    return safe_best_effort(
        _run,
        label="message_pipelines.two_phase_confirm",
        default=None,
    )


# ---------------------------------------------------------------------------
# Phase 10 — prequeue interrupt command.
# ---------------------------------------------------------------------------

def _phase_apply_prequeue_interrupt(
    text: str,
    session_key: str,
    handler: "ButlerMessageHandler",
) -> Optional[str]:
    """Phase: prequeue interrupt command (e.g. /停止)."""
    from butler.gateway.handler_helpers import _is_prequeue_interrupt_command

    if _is_prequeue_interrupt_command(text):
        return handler._format_prequeue_interrupt_reply(session_key)
    return None


# ---------------------------------------------------------------------------
# Phase 11 — pre-dispatch text rewrites (auto_continue + pre_gateway_dispatch).
# ---------------------------------------------------------------------------

def _phase_apply_pre_dispatch_rewrites(
    text: str,
    session_key: str,
    *,
    platform: str,
) -> Optional[str]:
    """Phase: rewrite text via auto_continue and pre_gateway_dispatch hooks.

    Returns ``None`` to mean "use original text", ``""`` to mean
    "drop this turn", or a non-empty string to mean "use as new text".

    Note: the original code did **not** wrap ``apply_pre_gateway_dispatch``
    in try/except — a hook failure propagated. We preserve that
    fail-loud behavior here on purpose.
    """
    from butler.gateway.handler_helpers import apply_auto_continue_rewrite

    continued = apply_auto_continue_rewrite(session_key, text)
    if continued:
        text = continued
    from butler.gateway.hooks import apply_pre_gateway_dispatch

    rewritten = apply_pre_gateway_dispatch(text, session_key=session_key, platform=platform)
    if rewritten is None:
        return None
    if not rewritten.strip():
        return ""
    return rewritten


# ---------------------------------------------------------------------------
# Phase 12 — inbound idempotency (Sprint 14 REL-11-1 reservation).
# ---------------------------------------------------------------------------

def _phase_apply_idempotency(
    text: str,
    session_key: str,
    *,
    external_id: str | None,
) -> tuple[Optional[str], bool, str]:
    """Phase: idempotency reservation.

    Returns ``(early_reply_or_None, reserved, inbound_id)``.
    ``reserved=True`` means the caller is responsible for calling
    ``complete_inbound`` in the ``finally`` block.
    """
    from butler.core.best_effort import safe_best_effort

    def _run() -> tuple[Optional[str], bool, str]:
        from butler.gateway.inbound_idempotency import (
            check_and_reserve_inbound,
            record_duplicate_skip,
        )
        from butler.session.keys import chat_id_from_session_key

        inbound_id = str(external_id or "").strip()
        if inbound_id and inbound_id == chat_id_from_session_key(session_key):
            inbound_id = ""
        _idem = check_and_reserve_inbound(
            session_key,
            inbound_id,
            text_preview=text[:80],
        )
        if _idem.skip:
            record_duplicate_skip(
                session_key,
                reason=_idem.reason,
                external_id=inbound_id,
                preview=text[:80],
            )
            return (_idem.user_reply or "（重复消息已忽略。）"), False, inbound_id
        return None, True, inbound_id

    return safe_best_effort(
        _run,
        label="message_pipelines.idempotency",
        default=(None, False, ""),
    )


# ---------------------------------------------------------------------------
# Phase 13 — session initializing (warmup + queue while spinning up).
# ---------------------------------------------------------------------------

def _phase_apply_session_initializing(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
    orchestrator: Any,
) -> Optional[str]:
    """Phase: session-initializing warmup. Returns early ack or None."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> Optional[str]:
        from butler.gateway.message_queue import (
            enqueue_inbound,
            format_initializing_ack,
            pending_count,
        )
        from butler.gateway.session_lifecycle import (
            session_initializing_enabled,
            try_enter_session,
        )

        if not session_initializing_enabled():
            return None

        state = try_enter_session(session_key, lambda: _warm_session_skills(orchestrator))
        if state != "queued":
            return None
        if enqueue_inbound(
            session_key,
            text,
            platform=platform,
            external_id=external_id or "",
        ):
            return format_initializing_ack(pending=pending_count(session_key))
        return format_initializing_ack()

    return safe_best_effort(
        _run,
        label="message_pipelines.session_initializing",
        default=None,
    )


# ---------------------------------------------------------------------------
# Phase 14 — queue inbound (steer / interrupt / collect / followup).
# ---------------------------------------------------------------------------

def _phase_apply_queue_inbound(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
    handler: "ButlerMessageHandler",
) -> Optional[str]:
    """Phase: enqueue or steer per queue_mode; return ack or None.

    Note: the original code did **not** wrap the queue logic in
    try/except — a queue failure propagated. We preserve that
    fail-loud behavior here on purpose.
    """
    if not handler._should_queue_inbound(session_key, text):
        return None
    from butler.gateway.message_queue import (
        enqueue_inbound,
        format_queued_ack,
        pending_count,
    )
    from butler.gateway.queue_settings import get_queue_mode

    mode = get_queue_mode(session_key)
    if mode == "steer":
        from butler.core.steer import (
            format_steer_gateway_reply,
            is_run_active,
            steer,
        )

        if is_run_active(session_key) and steer(text, session_key=session_key):
            return format_steer_gateway_reply(accepted=True, active=True)
        return None
    if mode == "interrupt":
        handler._format_prequeue_interrupt_reply(session_key)
        return None
    if enqueue_inbound(
        session_key,
        text,
        platform=platform,
        external_id=external_id or "",
    ):
        return format_queued_ack(
            pending=pending_count(session_key),
            session_key=session_key,
        )
    from butler.gateway.queue_settings import session_drop_policy

    if session_drop_policy(session_key) == "new":
        return "队列已满，最新消息未入队。可发 /queue 调整 cap 或 /诊断 查看。"
    return format_queued_ack(pending=pending_count(session_key), session_key=session_key)


# ---------------------------------------------------------------------------
# Phase 15 — reply admission (single-flight gate).
# ---------------------------------------------------------------------------

def _phase_apply_admission(text: str, session_key: str) -> Optional[Any]:
    """Phase: try_admit. Returns admission token (caller releases) or None."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> Any:
        from butler.gateway.reply_admission import try_admit

        return try_admit(session_key)

    return safe_best_effort(
        _run,
        label="message_pipelines.reply_admission",
        default=True,
    )


def queue_inbound_for_admission_failure(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
) -> str:
    """When ``try_admit`` returns ``None`` we either enqueue or reply."""
    from butler.core.best_effort import safe_best_effort

    def _run() -> Optional[str]:
        from butler.gateway.message_queue import (
            enqueue_inbound,
            format_queued_ack,
            pending_count,
        )

        if enqueue_inbound(
            session_key,
            text,
            platform=platform,
            external_id=external_id or "",
        ):
            return format_queued_ack(
                pending=pending_count(session_key),
                session_key=session_key,
            )
        return None

    queued = safe_best_effort(
        _run,
        label="message_pipelines.admission_failure_enqueue",
        default=None,
    )
    if queued:
        return queued
    return "会话处理中，请稍候…"
