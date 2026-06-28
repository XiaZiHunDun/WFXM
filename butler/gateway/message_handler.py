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
from butler.gateway.locked_phases import (
    LockedTurnState,
    _phase_apply_correction_intent,
    _phase_apply_github_issues_intent,
    _phase_apply_normalizers_and_slash,
    _phase_apply_prompt_hooks,
    _phase_augment_prompt,
    _phase_execute_turn,
    _phase_finalize_turn,
    _phase_format_error_card,
    _phase_format_turn_response,
    _phase_hygiene_compress,
    _phase_init_loop_role,
    _phase_prefetch_and_callbacks,
    _phase_resolve_turn_budget,
    _phase_validate_loop_messages,
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
from butler.tools.registry import dispatch_tool
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
        pm = self._orchestrator.project_manager
        project = pm.get_current(session_key=session_key)
        proj_name = (
            str(getattr(project, "name", "") or "").strip()
            or pm.resolve_active_project_name(session_key=session_key)
        )
        from butler.project.lead import gateway_loop_role
        from butler.tools.project_tools import get_tool_definitions_for_project

        from butler.plan.mode import is_plan_mode

        loop_role = gateway_loop_role(proj_name, project=project)
        if is_plan_mode(session_key):
            loop_role = "plan"
        tools = get_tool_definitions_for_project(project, role=loop_role)
        loop = self._orchestrator.create_agent_loop(
            role=loop_role,
            tools=tools,
            tool_dispatcher=dispatch_tool,
            session_key=session_key,
        )
        _inject_previous_session_summary(loop, project)
        from butler.core.session_hydration import hydrate_loop_on_create

        hydrate_loop_on_create(loop, session_key, project)
        return loop

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
        try:
            from butler.runtime.delegate_registry import interrupt_delegates_for_session

            n = interrupt_delegates_for_session(session_key)
            if n:
                logger.info("Gateway interrupted %d delegate loop(s) session=%s", n, session_key)
        except Exception as exc:
            logger.debug("Delegate interrupt skipped: %s", exc)
        loop = self._sessions.get(session_key)
        if loop is not None and hasattr(loop, "interrupt"):
            try:
                loop.interrupt()
                logger.info("Gateway interrupt requested session=%s", session_key)
            except Exception as exc:
                logger.debug("Gateway interrupt failed: %s", exc)

    def _format_prequeue_interrupt_reply(self, session_key: str) -> str:
        """Sprint 16 TST-10-5 第八批: 抽自 handle_message pre-dispatch hook (原 line 422-424).

        中断 in-flight session loop, 返 "已请求停止" 提示. 防御性 try/except 包裹 interrupt 调用,
        即使 interrupt 抛异常也返消息 (logger.debug), 不应阻断 caller.
        """
        try:
            self._interrupt_session_loop(session_key)
        except Exception as exc:
            logger.debug("Prequeue interrupt failed: %s", exc)
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
        """In-session pipeline orchestrator.

        R1-6: this method is now a thin orchestrator that wires the
        in-session phase functions from
        :mod:`butler.gateway.locked_phases` together. The body is
        reduced from ~272 non-blank lines to a linear flow of phase
        calls plus a single try/except for telemetry + error card
        rendering.
        """
        if not text.strip():
            return ""

        from butler.gateway.handler_helpers import _maybe_welcome_prefix

        state = LockedTurnState(
            text=text, session_key=session_key, platform=platform, external_id=external_id,
        )
        welcome_prefix = _maybe_welcome_prefix(session_key, text)

        from butler.gateway.owner_delegate_shortcuts import (
            resolve_project_context,
            try_expand_owner_edit_slash,
        )
        from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

        _pname, _pws = resolve_project_context(self._orchestrator, session_key)
        _expanded = try_expand_owner_edit_slash(state.text, project_name=_pname)
        if _expanded:
            state.text = _expanded
        else:
            _ingest = try_expand_owner_ingest_phrase(
                state.text,
                project_name=_pname,
                workspace=_pws,
            )
            if _ingest:
                state.text = _ingest

        response = _phase_apply_normalizers_and_slash(self, state)
        if response is not None:
            return response

        response = _phase_apply_correction_intent(self, state)
        if response is not None:
            return response

        response = _phase_apply_github_issues_intent(self, state)
        if response is not None:
            from butler.gateway.gateway_transcript import record_gateway_tool_action

            record_gateway_tool_action(
                state.session_key,
                tool_name="mcp_github_lst_repo_issues",
                args_preview=state.text.strip()[:400],
            )
            return response

        _phase_init_loop_role(self, state)
        state.turn_started = _time.monotonic()
        logger.info(
            "Gateway turn start session=%s platform=%s preview=%r",
            session_key,
            platform,
            text[:80],
        )

        response = _phase_apply_prompt_hooks(state)
        if response is not None:
            return response

        from butler.execution_context import use_execution_context

        with use_execution_context(self._orchestrator, session_key=session_key):
            _phase_augment_prompt(self, state)
            state.loop = self._get_or_create_loop(session_key)
            state.original_loop_config = state.loop.config
            try:
                response = _phase_validate_loop_messages(state)
                if response is not None:
                    return response
                _phase_resolve_turn_budget(state)
                _phase_hygiene_compress(self, state)
                _phase_prefetch_and_callbacks(self, state)
                _phase_execute_turn(state)
                _phase_finalize_turn(self, state)
                _phase_format_turn_response(self, state, welcome_prefix=welcome_prefix)
                return state.out
            except Exception as exc:
                state.health["error"] = str(exc)
                self._session_registry.set_health(session_key, state.health)
                logger.error(
                    "Message handling failed session=%s elapsed=%.1fs: %s",
                    session_key,
                    _time.monotonic() - state.turn_started,
                    exc,
                    exc_info=True,
                )
                card = _phase_format_error_card(exc, _time.monotonic() - state.turn_started)
                from butler.gateway.user_errors import format_gateway_user_error

                return card or format_gateway_user_error(exc)
            finally:
                state.loop.config = state.original_loop_config

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
        """Handle Butler slash commands. Returns response or None."""
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        import butler.gateway.commands  # noqa: F401 — ensure handlers registered
        from butler.gateway.command_registry import CommandContext, dispatch

        ctx = CommandContext(
            cmd=cmd,
            arg=arg,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
            orchestrator=self._orchestrator,
            session_registry=self._session_registry,
        )
        handled, result = dispatch(ctx)
        if handled:
            return result

        return None

    def _format_health_summary(self, session_key: str = "default") -> str:
        from butler.ops.health_report import (
            HealthReportInput,
            build_health_report,
            collect_mem_stats_for_health,
        )

        health = self.last_health_summary(session_key)
        return build_health_report(
            HealthReportInput(
                session_key=session_key,
                health=health,
                tool_summary=_tool_audit_summary(session_key),
                mem_stats=collect_mem_stats_for_health(
                    self._orchestrator, session_key, health
                ),
                orchestrator=self._orchestrator,
            )
        )

    def _format_response(self, result: LoopResult, platform: str) -> str:
        """Format the response appropriately for the platform."""
        if platform in ("wechat", "weixin"):
            from butler.report.format import wechat_response_text

            return wechat_response_text(result)

        if not result.final_response:
            return "（执行完成，无文字输出）"
        return result.final_response


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
