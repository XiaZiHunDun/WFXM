"""Butler Gateway Message Handler.

Processes incoming messages from any platform (WeChat, Telegram, etc.)
through Butler's orchestration layer. Provides the bridge between
external gateways and Butler's AgentLoop.

Information flow:
  User -> Platform Adapter -> Butler Handler -> AgentLoop -> Report Pipeline -> User

R1-6 (audit ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-6):
The two god methods ``handle_message`` and ``_handle_message_locked``
have been decomposed into composable phase functions living in
:mod:`butler.gateway.message_pipelines` (pre-session phases) and
:mod:`butler.gateway.locked_phases` (in-session phases). This module
keeps the class definition, the per-session AgentLoop bookkeeping,
and a thin orchestrator that wires the phases together.
"""

from __future__ import annotations

import logging
import os
import time as _time
from typing import Any, Optional

from butler.core.agent_loop import AgentLoop, LoopResult
from butler.gateway.message_handler_ops import (
    interrupt_session_loop_safe,
    run_prequeue_interrupt_safe,
)
from butler.gateway.message_pipelines import (
    _phase_apply_admission,
    _phase_apply_idempotency,
    _phase_apply_queue_inbound,
    _phase_apply_session_initializing,
    _phase_resolve_session_key,
    _phase_transform_inbound_text,
)
from butler.orchestrator import ButlerOrchestrator
from butler.session.keys import normalize_session_key
from butler.session.lifecycle import attach_turn_memory_prefetch, sync_turn_memory
from butler.gateway.session_registry import GatewaySessionRegistry

logger = logging.getLogger(__name__)


class ButlerMessageHandler:
    """Handles messages from any platform through Butler's pipeline.

    The handler maintains per-session AgentLoop instances and routes
    messages through Butler's orchestration layer. After the R1-6
    split, the two big methods (``handle_message`` and
    ``_handle_message_locked``) are thin orchestrators that wire
    the phase functions in :mod:`message_pipelines` and
    :mod:`locked_phases` together.
    """

    def __init__(
        self,
        channel: str = "gateway",
        orchestrator: Optional[ButlerOrchestrator] = None,
    ):
        self.channel = channel
        self._orchestrator = orchestrator or ButlerOrchestrator(user_id="owner", channel=channel)
        self._session_registry = GatewaySessionRegistry(
            self._create_loop_for_session,
            finalize=self._finalize_session,
            on_session_removed=_on_gateway_session_removed,
            max_sessions=_env_int("BUTLER_GATEWAY_MAX_SESSIONS", 128),
            idle_ttl_seconds=_env_float("BUTLER_GATEWAY_SESSION_IDLE_TTL_SECONDS", 7200),
        )
        self._sessions: dict[str, AgentLoop] = self._session_registry.sessions
        self._health_by_session: dict[str, dict[str, Any]] = self._session_registry.health_by_session
        from butler.gateway.inbound_pipeline import build_default_inbound_pipeline

        self._inbound_pipeline = build_default_inbound_pipeline()

    def _create_loop_for_session(self, session_key: str) -> AgentLoop:
        from butler.gateway.session_loop_factory import create_gateway_loop

        return create_gateway_loop(self, session_key)

    def _finalize_session(self, loop: AgentLoop) -> None:
        from butler.session.lifecycle import trigger_session_end

        trigger_session_end(self._orchestrator, loop, reason="finalize")

    def _get_or_create_loop(self, session_key: str) -> AgentLoop:
        self._session_registry.evict_idle()
        return self._session_registry.get_or_create(session_key)

    def resolve_session_key(
        self,
        *,
        platform: str = "unknown",
        external_id: str | None = None,
        session_key: str | None = None,
    ) -> str:
        """Resolve ``platform:chat_id:project`` from external id and per-chat project."""
        pm = self._orchestrator.project_manager
        cid = str(external_id or "").strip()
        if not cid and session_key:
            from butler.session.keys import chat_id_from_session_key

            cid = chat_id_from_session_key(session_key)
        project = pm.get_project_name_for_chat(platform=platform, chat_id=cid or "default")
        return normalize_session_key(
            platform=platform,
            external_id=external_id,
            session_key=session_key,
            project=project,
        )

    def _should_queue_inbound(self, session_key: str, text: str) -> bool:
        from butler.gateway.message_queue import message_queue_enabled

        if not message_queue_enabled():
            return False
        stripped = (text or "").strip()
        if not stripped or stripped.startswith("/"):
            return False
        return self._session_registry.is_session_active(session_key)

    def _queue_push_via_bridge(self) -> bool:
        from butler.env_parse import env_truthy

        return env_truthy("BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE", default=True)

    def _interrupt_session_loop(self, session_key: str) -> None:
        interrupt_session_loop_safe(self._sessions, session_key)

    def _format_prequeue_interrupt_reply(self, session_key: str) -> str:
        """Sprint 16 TST-10-5 第八批: 抽自 handle_message pre-dispatch hook (原 line 422-424).

        中断 in-flight session loop, 返 "已请求停止" 提示. 防御性 try/except 包裹 interrupt 调用,
        即使 interrupt 抛异常也返消息 (logger.debug), 不应阻断 caller.
        """
        run_prequeue_interrupt_safe(
            lambda: self._interrupt_session_loop(session_key),
            log_debug=logger.debug,
        )
        return "已请求停止当前会话任务（含进行中的委派）。"

    def _drain_queued_inbound(
        self,
        session_key: str,
        *,
        platform: str,
        external_id: str | None,
        primary_reply: str = "",
    ) -> str:
        from butler.gateway.inbound_drain import drain_queued_inbound

        return drain_queued_inbound(
            self,
            session_key,
            platform=platform,
            external_id=external_id,
            primary_reply=primary_reply,
        )

    def _recover_registry_if_stale(self) -> None:
        """Clear a stuck ``reset_all`` flag that would block ``enter_session`` forever."""
        reg = self._session_registry
        with reg._lock:
            if (
                reg._resetting_all
                and not reg._active_sessions
                and reg._pending_session_entries == 0
            ):
                logger.warning("Recovering stale gateway reset_all flag")
                reg._resetting_all = False
                reg._reset_condition.notify_all()

    def handle_message(
        self,
        text: str,
        *,
        session_key: str | None = None,
        platform: str = "unknown",
        external_id: str | None = None,
    ) -> str:
        """Process an incoming message and return the response.

        R1-6: this method is now a thin orchestrator that wires the
        pre-session phase functions from
        :mod:`butler.gateway.message_pipelines` together. The body is
        reduced from ~334 non-blank lines to a linear flow of phase
        calls; each phase encapsulates one inbound guard, transform,
        or admission step.
        """
        _t0 = _time.monotonic()
        self._recover_registry_if_stale()
        logger.info(
            "Gateway handle_message start platform=%s external_id=%s preview=%r",
            platform,
            external_id,
            (text or "")[:80],
        )

        session_key = _phase_resolve_session_key(
            self, platform=platform, external_id=external_id, session_key=session_key,
        )
        text = _phase_transform_inbound_text(
            text, platform=platform, external_id=external_id, session_key=session_key,
        )

        if not text.strip():
            return ""

        chat_id = str(external_id or "").strip()
        from butler.gateway.delegate_push_dedup import gateway_inbound_guard

        with gateway_inbound_guard(chat_id):
            from butler.gateway.turn_post_pipeline import run_turn_post_inbound_pipeline

            return run_turn_post_inbound_pipeline(
                self,
                text,
                session_key=session_key,
                platform=platform,
                external_id=external_id,
                t0=_t0,
            )

    def _handle_message_after_pipeline(
        self,
        text: str,
        *,
        session_key: str | None,
        platform: str,
        external_id: str | None,
        _t0: float,
    ) -> str:
        """Backward-compatible alias; prefer :func:`turn_post_pipeline.run_turn_post_inbound_pipeline`."""
        from butler.gateway.turn_post_pipeline import run_turn_post_inbound_pipeline

        return run_turn_post_inbound_pipeline(
            self,
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
            t0=_t0,
        )

    def _handle_message_locked(
        self,
        text: str,
        *,
        session_key: str = "default",
        platform: str = "unknown",
        external_id: str | None = None,
    ) -> str:
        """In-session pipeline orchestrator (ENG-3 → locked_turn_orchestrator)."""
        from butler.gateway.locked_turn_orchestrator import run_locked_message_turn

        return run_locked_message_turn(
            self,
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )

    def last_health_summary(self, session_key: str = "default") -> dict[str, Any]:
        """Return the latest best-effort runtime diagnostics for a session."""
        return self._session_registry.get_health(session_key)

    def _handle_command(
        self,
        text: str,
        *,
        session_key: str = "default",
        platform: str = "unknown",
        external_id: str | None = None,
    ) -> Optional[str]:
        from butler.gateway.handler_commands import handle_slash_command

        return handle_slash_command(
            self,
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )

    def _format_health_summary(self, session_key: str = "default") -> str:
        from butler.gateway.handler_commands import format_health_summary

        return format_health_summary(self, session_key)

    def _format_response(self, result: LoopResult, platform: str) -> str:
        from butler.gateway.handler_commands import format_loop_response

        return format_loop_response(result, platform)


from butler.gateway.handler_helpers import (  # noqa: F401, E402
    _normalize_switch_request,
    _normalize_status_request,
    _normalize_new_session_request,
    _normalize_detail_request,
    _normalize_memo_request,
    _normalize_contacts_request,
    _normalize_expense_request,
    _normalize_habits_request,
    _gateway_run_callbacks,
    _is_prequeue_interrupt_command,
    _env_int,
    _env_float,
    _is_sessionless_command,
    apply_auto_continue_rewrite,
    _tool_audit_summary,
    _reset_tool_audit_events,
    _maybe_welcome_prefix,
    _build_project_overview,
    _inject_previous_session_summary,
    _on_gateway_session_removed,
    _WELCOMED_SESSIONS,
    _WELCOME_TEXT,
)
