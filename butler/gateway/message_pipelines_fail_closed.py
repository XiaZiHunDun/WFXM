"""Fail-closed inbound security guards for message pipelines (P0-A)."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def apply_io_guardrail_fail_closed(text: str) -> Optional[str]:
    from butler.gateway.message_pipelines_fail_closed_ops import run_fail_closed_guard

    def _run() -> Optional[str]:
        from butler.core.io_guardrail import check_inbound_text, io_guardrail_enabled

        if io_guardrail_enabled():
            guard = check_inbound_text(text)
            if guard.tripwire and not guard.allowed:
                return guard.user_message or "消息未通过入站安全检查。"
        return None

    return run_fail_closed_guard(
        _run,
        label="io_guardrail",
        blocked_message="安全检查模块异常，消息已拦截。请稍后重试。",
    )


def apply_human_gate_fail_closed(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
) -> Optional[str]:
    from butler.gateway.message_pipelines_fail_closed_ops import run_fail_closed_guard

    def _run() -> Optional[str]:
        from butler.human_gate import resolve_human_gate_message

        from butler.gateway.owner_gate import is_gateway_owner

        is_owner = is_gateway_owner(platform=platform, external_id=external_id)
        gate_reply = resolve_human_gate_message(
            session_key, text, owner_verified=is_owner,
        )
        if gate_reply is not None:
            return gate_reply
        return None

    return run_fail_closed_guard(
        _run,
        label="human_gate",
        blocked_message="审批门控模块异常，消息已拦截。请稍后重试。",
    )


def apply_injection_guard_fail_closed(
    text: str,
    session_key: str,
    *,
    record_injection_transcript,
) -> tuple[str, Optional[str]]:
    from butler.gateway.message_pipelines_fail_closed_ops import (
        run_injection_guard_fail_closed,
    )

    def _run() -> tuple[str, None]:
        from butler.memory.injection_guard import (
            injection_score_enabled,
            mark_adversarial_user_text,
            score_injection_risk,
        )

        if injection_score_enabled():
            risk = score_injection_risk(text)
            if risk > 0:
                record_injection_transcript(
                    session_key,
                    "injection_score",
                    risk,
                    text,
                    label="message_pipelines.injection_score_transcript",
                )
        return mark_adversarial_user_text(text), None

    return run_injection_guard_fail_closed(
        _run,
        label="injection_guard",
        text=text,
        blocked_message="注入检测模块异常，消息已拦截。请稍后重试。",
    )


def apply_injection_llm_fail_closed(
    text: str,
    session_key: str,
    *,
    record_injection_transcript,
) -> Optional[str]:
    from butler.gateway.message_pipelines_fail_closed_ops import run_fail_closed_guard

    def _run() -> Optional[str]:
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
            record_injection_transcript(
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

    return run_fail_closed_guard(
        _run,
        label="injection_llm_score",
        blocked_message="LLM 注入检测模块异常，消息已拦截。请稍后重试。",
    )


__all__ = [
    "apply_human_gate_fail_closed",
    "apply_injection_guard_fail_closed",
    "apply_injection_llm_fail_closed",
    "apply_io_guardrail_fail_closed",
]
