"""Inbound pre-processing pipeline extracted from ``ButlerMessageHandler.handle_message``."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Protocol

from butler.gateway.inbound_idempotency import release_inflight
from butler.gateway.handler_helpers import (
    _is_prequeue_interrupt_command,
    _is_sessionless_command,
)
from butler.session.keys import chat_id_from_session_key

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class InboundResult:
    text: str
    short_circuit: str | None = None
    idempotency_reserved: bool = False
    inbound_id: str = ""


class InboundHandlerRef(Protocol):
    """Minimal handler surface used by ``run_inbound_pipeline``."""

    _session_registry: Any
    _orchestrator: Any

    def _should_queue_inbound(self, session_key: str, text: str) -> bool: ...

    def _interrupt_session_loop(self, session_key: str) -> None: ...

    def _queue_push_via_bridge(self) -> bool: ...

    def _handle_message_locked(
        self,
        text: str,
        *,
        session_key: str,
        platform: str,
        external_id: str | None,
    ) -> str: ...


def run_inbound_pipeline(
    text: str,
    *,
    session_key: str,
    platform: str,
    external_id: str | None,
    handler_ref: InboundHandlerRef,
) -> InboundResult:
    import time as _time

    _t0 = _time.monotonic()
    try:
        from butler.core.message_ir import inbound_text_from_gateway

        text = inbound_text_from_gateway(
            text,
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )
    except Exception as exc:
        logger.debug("Inbound text transform skipped: %s", exc)
    try:
        from butler.mcp.profiles import (
            mcp_profiles_enabled,
            select_profile_for_text,
            set_session_profile,
        )

        if mcp_profiles_enabled() and text.strip():
            set_session_profile(
                session_key,
                select_profile_for_text(text),
            )
    except Exception as exc:
        logger.debug("MCP profile selection skipped: %s", exc)
    if not text.strip():
        return InboundResult(text=text, short_circuit="")

    try:
        from butler.core.io_guardrail import check_inbound_text, io_guardrail_enabled

        if io_guardrail_enabled():
            guard = check_inbound_text(text)
            if guard.tripwire and not guard.allowed:
                return InboundResult(
                    text=text,
                    short_circuit=guard.user_message or "消息未通过入站安全检查。",
                )
    except ImportError as exc:
        logger.info("io_guardrail module not available: %s", exc)
    except Exception as exc:
        logger.error("io_guardrail check raised — fail-closed: %s", exc)
        return InboundResult(text=text, short_circuit="安全检查模块异常，消息已拦截。请稍后重试。")

    try:
        from butler.human_gate import resolve_human_gate_message

        gate_reply = resolve_human_gate_message(session_key, text)
        if gate_reply is not None:
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

            if not is_gateway_owner(platform=platform, external_id=external_id):
                return InboundResult(text=text, short_circuit=owner_required_message())
            return InboundResult(text=text, short_circuit=gate_reply)
    except ImportError as exc:
        logger.info("human_gate module not available: %s", exc)
    except Exception as exc:
        logger.error("human_gate check raised — fail-closed: %s", exc)
        return InboundResult(text=text, short_circuit="审批门控模块异常，消息已拦截。请稍后重试。")

    try:
        from butler.memory.injection_guard import (
            injection_score_enabled,
            mark_adversarial_user_text,
            score_injection_risk,
        )

        if injection_score_enabled():
            risk = score_injection_risk(text)
            if risk > 0:
                try:
                    from butler.core.session_transcript import append_transcript_entry

                    append_transcript_entry(
                        session_key,
                        "injection_score",
                        {"score": risk, "preview": text[:120]},
                    )
                except Exception as exc:
                    logger.debug("Injection score transcript skipped: %s", exc)
        text = mark_adversarial_user_text(text)
    except ImportError as exc:
        logger.info("injection_guard module not available: %s", exc)
    except Exception as exc:
        logger.error("injection_guard raised — fail-closed: %s", exc)
        return InboundResult(text=text, short_circuit="注入检测模块异常，消息已拦截。请稍后重试。")

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

        if injection_llm_score_enabled():
            if consume_injection_bypass(session_key):
                pass
            elif has_injection_review_pending(session_key):
                hint = format_pending_hint(session_key)
                if hint:
                    return InboundResult(text=text, short_circuit=hint)
            else:
                blocked, llm_score, block_msg = should_block_inbound_llm_score(text)
                if llm_score is not None:
                    try:
                        from butler.core.session_transcript import append_transcript_entry

                        append_transcript_entry(
                            session_key,
                            "injection_llm_score",
                            {"score": llm_score, "preview": text[:120]},
                        )
                    except Exception as exc:
                        logger.debug("Injection LLM score transcript skipped: %s", exc)
                if blocked:
                    if injection_llm_gate_enabled() and llm_score is not None:
                        request_injection_review_gate(session_key, score=llm_score)
                        return InboundResult(
                            text=text,
                            short_circuit=format_pending_hint(session_key) or block_msg,
                        )
                    return InboundResult(text=text, short_circuit=block_msg)
    except ImportError as exc:
        logger.info("injection_llm_score module not available: %s", exc)
    except Exception as exc:
        logger.error("injection_llm_score raised — fail-closed: %s", exc)
        return InboundResult(text=text, short_circuit="LLM 注入检测模块异常，消息已拦截。请稍后重试。")

    _idempotency_reserved = False
    inbound_id = ""

    try:
        from butler.gateway.bot_loop_guard import record_and_should_suppress

        chat_id = session_key.split(":")[-1] if ":" in session_key else session_key
        suppress, _reason = record_and_should_suppress(
            chat_id=chat_id,
            sender_id=str(external_id or ""),
            text=text,
        )
        if suppress:
            if _idempotency_reserved:
                try:
                    release_inflight(session_key, external_id)
                except Exception as exc:
                    logger.debug("Inflight release skipped: %s", exc)
            return InboundResult(
                text=text,
                short_circuit="（已忽略：群聊 bot 互回复环防护）",
            )
    except Exception as exc:
        logger.debug("Bot loop guard skipped: %s", exc)

    try:
        from butler.core.two_phase_confirm import (
            cancel_pending_unless_confirm,
            try_execute_pending_confirm,
        )

        pending_reply = try_execute_pending_confirm(text, session_key=session_key)
        if pending_reply is not None:
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

            if not is_gateway_owner(platform=platform, external_id=external_id):
                return InboundResult(text=text, short_circuit=owner_required_message())
            return InboundResult(text=text, short_circuit=pending_reply)
        cancel_note = cancel_pending_unless_confirm(text, session_key=session_key)
        if cancel_note:
            text = f"{cancel_note}\n\n{text}"
    except Exception as exc:
        logger.debug("Two-phase confirm skipped: %s", exc)

    try:
        from butler.gateway.permission_commands import handle_permission_command

        perm_reply = handle_permission_command(
            text,
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )
        if perm_reply is not None:
            return InboundResult(text=text, short_circuit=perm_reply)
    except Exception as exc:
        logger.debug("Permission command handling skipped: %s", exc)

    try:
        from butler.tools.terminal_approval import parse_approve_command, store_approval

        pattern_raw = (text or "").strip()
        for prefix in ("/批准模式", "/approve-pattern"):
            if pattern_raw.lower().startswith(prefix.lower()):
                from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

                if not is_gateway_owner(platform=platform, external_id=external_id):
                    return InboundResult(text=text, short_circuit=owner_required_message())
                pat = pattern_raw[len(prefix) :].strip()
                if not pat:
                    return InboundResult(
                        text=text,
                        short_circuit="用法: /批准模式 <rm_rf|curl_pipe_sh|chmod_777|...>",
                    )
                from butler.tools.terminal_pattern_approval import approve_pattern

                approve_pattern(session_key, pat)
                return InboundResult(
                    text=text,
                    short_circuit=f"已批准本会话 terminal 危险模式「{pat}」（24h 内同类命令可放行）。",
                )
        cmd = parse_approve_command(text)
        if cmd is not None:
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

            if not is_gateway_owner(platform=platform, external_id=external_id):
                return InboundResult(text=text, short_circuit=owner_required_message())
            store_approval(cmd, session_key=session_key)
            return InboundResult(
                text=text,
                short_circuit=f"已批准 terminal 命令（5 分钟内有效）:\n{cmd[:200]}",
            )
    except Exception as exc:
        logger.debug("Terminal approval handling skipped: %s", exc)

    if _is_prequeue_interrupt_command(text):
        handler_ref._interrupt_session_loop(session_key)
        return InboundResult(text=text, short_circuit="已请求停止当前会话任务（含进行中的委派）。")

    try:
        from butler.core.auto_continue import resolve_auto_continue_user_message

        continued = resolve_auto_continue_user_message(session_key, text)
        if continued:
            text = continued
    except Exception as exc:
        logger.debug("Auto continue resolve skipped: %s", exc)

    from butler.gateway.hooks import apply_pre_gateway_dispatch

    rewritten = apply_pre_gateway_dispatch(text, session_key=session_key, platform=platform)
    if rewritten is not None:
        if not rewritten.strip():
            return InboundResult(text=text, short_circuit="")
        text = rewritten

    if _is_sessionless_command(text):
        out = handler_ref._handle_message_locked(
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )
        logger.info(
            "Gateway handle_message done (slash) session=%s elapsed=%.1fs out_len=%d",
            session_key,
            _time.monotonic() - _t0,
            len(out or ""),
        )
        return InboundResult(text=text, short_circuit=out)

    try:
        from butler.gateway.inbound_idempotency import (
            check_and_reserve_inbound,
            complete_inbound,
            record_duplicate_skip,
        )

        inbound_id = str(external_id or "").strip()
        if inbound_id and inbound_id == chat_id_from_session_key(session_key):
            # ``external_id`` is usually the platform chat/user id, not a per-message id.
            # Treating it as an idempotency key would suppress every later turn.
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
            return InboundResult(
                text=text,
                short_circuit=_idem.user_reply or "（重复消息已忽略。）",
            )
        _idempotency_reserved = True
    except Exception as exc:
        logger.debug("Idempotency check skipped: %s", exc)

    try:
        from butler.gateway.message_queue import (
            enqueue_inbound,
            format_queued_ack,
            pending_count,
        )
        from butler.gateway.session_lifecycle import (
            format_initializing_ack,
            session_initializing_enabled,
            try_enter_session,
        )

        if session_initializing_enabled():

            def _warm() -> None:
                try:
                    from butler.skills.similarity import _ensure_jieba

                    _ensure_jieba()
                except Exception as exc:
                    logger.debug("Jieba warm-up skipped: %s", exc)
                mgr = getattr(handler_ref._orchestrator, "_skill_manager", None)
                if mgr is not None:
                    mgr.list_skills()

            state = try_enter_session(session_key, _warm)
            if state == "queued":
                if enqueue_inbound(
                    session_key,
                    text,
                    platform=platform,
                    external_id=external_id or "",
                ):
                    return InboundResult(
                        text=text,
                        short_circuit=format_initializing_ack(pending=pending_count(session_key)),
                    )
                return InboundResult(
                    text=text,
                    short_circuit=format_initializing_ack(),
                )
    except Exception as exc:
        logger.debug("Session initializing skipped: %s", exc)

    if handler_ref._should_queue_inbound(session_key, text):
        from butler.gateway.message_queue import (
            enqueue_inbound,
            format_queued_ack,
            pending_count,
        )
        from butler.gateway.queue_settings import get_queue_mode

        mode = get_queue_mode(session_key)
        if mode == "steer":
            from butler.core.steer import format_steer_gateway_reply, is_run_active, steer

            if is_run_active(session_key) and steer(text, session_key=session_key):
                return InboundResult(
                    text=text,
                    short_circuit=format_steer_gateway_reply(accepted=True, active=True),
                )
        elif mode == "interrupt":
            handler_ref._interrupt_session_loop(session_key)
        else:
            if enqueue_inbound(
                session_key,
                text,
                platform=platform,
                external_id=external_id or "",
            ):
                return InboundResult(
                    text=text,
                    short_circuit=format_queued_ack(
                        pending=pending_count(session_key),
                        session_key=session_key,
                    ),
                )
            from butler.gateway.queue_settings import session_drop_policy

            if session_drop_policy(session_key) == "new":
                return InboundResult(
                    text=text,
                    short_circuit="队列已满，最新消息未入队。可发 /queue 调整 cap 或 /诊断 查看。",
                )
            return InboundResult(
                text=text,
                short_circuit=format_queued_ack(
                    pending=pending_count(session_key),
                    session_key=session_key,
                ),
            )

    return InboundResult(
        text=text,
        idempotency_reserved=_idempotency_reserved,
        inbound_id=inbound_id,
    )
