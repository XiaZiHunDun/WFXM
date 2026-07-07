"""Fail-closed inbound security guards for message pipelines (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional, cast

from butler.gateway.message_pipelines_fail_closed_ops import (
    run_fail_closed_guard,
    run_injection_guard_fail_closed,
)
from butler.core.io_guardrail import (
    check_inbound_text,
    io_guardrail_enabled,
)
from butler.human_gate import (
    resolve_human_gate_message,
    consume_injection_bypass,
    format_pending_hint,
    has_injection_review_pending,
    request_injection_review_gate,
)
from butler.gateway.owner_gate import is_gateway_owner
from butler.memory.injection_guard import (
    injection_score_enabled,
    mark_adversarial_user_text,
    score_injection_risk,
)
from butler.memory.injection_llm_score import (
    injection_llm_gate_enabled,
    injection_llm_score_enabled,
    should_block_inbound_llm_score,
)

logger = logging.getLogger(__name__)

_RecordInjectionTranscript = Callable[..., None]


def apply_io_guardrail_fail_closed(text: str) -> Optional[str]:

    def _run() -> Optional[str]:

        if io_guardrail_enabled():
            guard = check_inbound_text(text)
            if guard.tripwire and not guard.allowed:
                return cast(
                    str,
                    guard.user_message or "消息未通过入站安全检查。",
                )
        return None

    return cast(
        Optional[str],
        run_fail_closed_guard(
            _run,
            label="io_guardrail",
            blocked_message="安全检查模块异常，消息已拦截。请稍后重试。",
        ),
    )


def apply_human_gate_fail_closed(
    text: str,
    session_key: str,
    *,
    platform: str,
    external_id: str | None,
) -> Optional[str]:

    def _run() -> Optional[str]:


        is_owner = is_gateway_owner(platform=platform, external_id=external_id)
        gate_reply = resolve_human_gate_message(
            session_key, text, owner_verified=is_owner,
        )
        if gate_reply is not None:
            return cast(str, gate_reply)
        return None

    return cast(
        Optional[str],
        run_fail_closed_guard(
            _run,
            label="human_gate",
            blocked_message="审批门控模块异常，消息已拦截。请稍后重试。",
        ),
    )


def apply_injection_guard_fail_closed(
    text: str,
    session_key: str,
    *,
    record_injection_transcript: _RecordInjectionTranscript,
) -> tuple[str, Optional[str]]:

    def _run() -> tuple[str, None]:

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
        return cast(str, mark_adversarial_user_text(text)), None

    return cast(
        tuple[str, Optional[str]],
        run_injection_guard_fail_closed(
            _run,
            label="injection_guard",
            text=text,
            blocked_message="注入检测模块异常，消息已拦截。请稍后重试。",
        ),
    )


def apply_injection_llm_fail_closed(
    text: str,
    session_key: str,
    *,
    record_injection_transcript: _RecordInjectionTranscript,
) -> Optional[str]:

    def _run() -> Optional[str]:

        if not injection_llm_score_enabled():
            return None
        if consume_injection_bypass(session_key):
            return None
        if has_injection_review_pending(session_key):
            hint = format_pending_hint(session_key)
            if hint:
                return cast(str, hint)
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
            return cast(
                str,
                format_pending_hint(session_key) or block_msg,
            )
        return cast(str, block_msg)

    return cast(
        Optional[str],
        run_fail_closed_guard(
            _run,
            label="injection_llm_score",
            blocked_message="LLM 注入检测模块异常，消息已拦截。请稍后重试。",
        ),
    )


__all__ = [
    "apply_human_gate_fail_closed",
    "apply_injection_guard_fail_closed",
    "apply_injection_llm_fail_closed",
    "apply_io_guardrail_fail_closed",
]
