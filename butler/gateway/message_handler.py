"""Butler Gateway Message Handler.

Processes incoming messages from any platform (WeChat, Telegram, etc.)
through Butler's orchestration layer. Provides the bridge between
external gateways and Butler's AgentLoop.

Information flow:
  User -> Platform Adapter -> Butler Handler -> AgentLoop -> Report Pipeline -> User
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from butler.orchestrator import ButlerOrchestrator
from butler.session.keys import chat_id_from_session_key, normalize_session_key
from butler.core.agent_loop import AgentLoop, LoopResult, LoopStatus
from butler.session.lifecycle import attach_turn_memory_prefetch, sync_turn_memory
from butler.tools.registry import dispatch_tool
from butler.gateway.session_registry import GatewaySessionRegistry
from butler.gateway.inbound_idempotency import release_inflight

logger = logging.getLogger(__name__)


class ButlerMessageHandler:
    """Handles messages from any platform through Butler's pipeline.

    The handler maintains per-session AgentLoop instances and routes
    messages through Butler's orchestration layer.
    """

    def __init__(self, channel: str = "gateway"):
        self.channel = channel
        self._orchestrator = ButlerOrchestrator(user_id="owner", channel=channel)
        self._session_registry = GatewaySessionRegistry(
            self._create_loop_for_session,
            finalize=self._finalize_session,
            on_session_removed=_on_gateway_session_removed,
            max_sessions=_env_int("BUTLER_GATEWAY_MAX_SESSIONS", 128),
            idle_ttl_seconds=_env_float("BUTLER_GATEWAY_SESSION_IDLE_TTL_SECONDS", 7200),
        )
        self._sessions: dict[str, AgentLoop] = self._session_registry.sessions
        self._health_by_session: dict[str, dict[str, Any]] = self._session_registry.health_by_session

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

    def _drain_queued_inbound(
        self,
        session_key: str,
        *,
        platform: str,
        external_id: str | None,
        primary_reply: str = "",
    ) -> str:

        from butler.gateway.message_queue import (
            message_queue_enabled,
            pop_all_merged,
            pop_next,
        )
        from butler.gateway.queue_settings import get_queue_mode

        if not message_queue_enabled():
            return ""

        mode = get_queue_mode(session_key)
        parts: list[str] = []

        if mode == "collect":
            item = pop_all_merged(session_key)
            if item is not None and not self._session_registry.is_session_active(session_key):
                logger.info(
                    "Gateway drain collect session=%s preview=%r",
                    session_key,
                    item.text[:80],
                )
                part = self.handle_message(
                    item.text,
                    session_key=session_key,
                    platform=item.platform or platform,
                    external_id=item.external_id or external_id,
                )
                if part:
                    parts.append(part)
        else:
            try:
                max_drain = max(0, int(os.getenv("BUTLER_GATEWAY_QUEUE_DRAIN_PER_TURN", "1") or "1"))
            except ValueError:
                max_drain = 1
            if mode == "followup":
                try:
                    max_drain = max(max_drain, int(os.getenv("BUTLER_GATEWAY_QUEUE_DRAIN_FOLLOWUP", "1") or "1"))
                except ValueError:
                    pass
            for _ in range(max_drain):
                item = pop_next(session_key)
                if item is None:
                    break
                if self._session_registry.is_session_active(session_key):
                    break
                logger.info(
                    "Gateway drain queued session=%s priority=%s preview=%r",
                    session_key,
                    item.priority,
                    item.text[:60],
                )
                part = self.handle_message(
                    item.text,
                    session_key=session_key,
                    platform=item.platform or platform,
                    external_id=item.external_id or external_id,
                )
                if part:
                    parts.append(part)

        if not parts:
            return ""
        combined = "\n\n---\n\n".join(parts) if len(parts) > 1 else parts[0]
        if self._queue_push_via_bridge() and primary_reply.strip():
            from butler.gateway.outbound_bridge import get_current_bridge

            br = get_current_bridge()
            if br is not None:
                br.schedule_supplementary_reply(combined, kind="queued")
                return ""
        return combined

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

        This is the main entry point for all platform messages.
        Returns formatted text appropriate for the platform.
        """
        import time as _time

        _t0 = _time.monotonic()
        self._recover_registry_if_stale()
        logger.info(
            "Gateway handle_message start platform=%s external_id=%s preview=%r",
            platform,
            external_id,
            (text or "")[:80],
        )

        session_key = self.resolve_session_key(
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )
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
            return ""

        try:
            from butler.core.io_guardrail import check_inbound_text, io_guardrail_enabled

            if io_guardrail_enabled():
                guard = check_inbound_text(text)
                if guard.tripwire and not guard.allowed:
                    return guard.user_message or "消息未通过入站安全检查。"
        except ImportError:
            pass
        except Exception as exc:
            logger.error("io_guardrail check raised — fail-closed: %s", exc)
            return "安全检查模块异常，消息已拦截。请稍后重试。"

        try:
            from butler.human_gate import resolve_human_gate_message

            gate_reply = resolve_human_gate_message(session_key, text)
            if gate_reply is not None:
                return gate_reply
        except ImportError:
            pass
        except Exception as exc:
            logger.error("human_gate check raised — fail-closed: %s", exc)
            return "审批门控模块异常，消息已拦截。请稍后重试。"

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
        except ImportError:
            pass
        except Exception as exc:
            logger.error("injection_guard raised — fail-closed: %s", exc)
            return "注入检测模块异常，消息已拦截。请稍后重试。"

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
                        return hint
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
                            return format_pending_hint(session_key) or block_msg
                        return block_msg
        except ImportError:
            pass
        except Exception as exc:
            logger.error("injection_llm_score raised — fail-closed: %s", exc)
            return "LLM 注入检测模块异常，消息已拦截。请稍后重试。"

        _idempotency_reserved = False

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
                return "（已忽略：群聊 bot 互回复环防护）"
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
                    return owner_required_message()
                return pending_reply
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
                return perm_reply
        except Exception as exc:
            logger.debug("Permission command handling skipped: %s", exc)

        try:
            from butler.tools.terminal_approval import parse_approve_command, store_approval

            pattern_raw = (text or "").strip()
            for prefix in ("/批准模式", "/approve-pattern"):
                if pattern_raw.lower().startswith(prefix.lower()):
                    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

                    if not is_gateway_owner(platform=platform, external_id=external_id):
                        return owner_required_message()
                    pat = pattern_raw[len(prefix) :].strip()
                    if not pat:
                        return "用法: /批准模式 <rm_rf|curl_pipe_sh|chmod_777|...>"
                    from butler.tools.terminal_pattern_approval import approve_pattern

                    approve_pattern(session_key, pat)
                    return f"已批准本会话 terminal 危险模式「{pat}」（24h 内同类命令可放行）。"
            cmd = parse_approve_command(text)
            if cmd is not None:
                from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

                if not is_gateway_owner(platform=platform, external_id=external_id):
                    return owner_required_message()
                store_approval(cmd, session_key=session_key)
                return f"已批准 terminal 命令（5 分钟内有效）:\n{cmd[:200]}"
        except Exception as exc:
            logger.debug("Terminal approval handling skipped: %s", exc)

        if _is_prequeue_interrupt_command(text):
            self._interrupt_session_loop(session_key)
            return "已请求停止当前会话任务（含进行中的委派）。"

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
                return ""
            text = rewritten

        if _is_sessionless_command(text):
            out = self._handle_message_locked(
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
            return out

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
                return _idem.user_reply or "（重复消息已忽略。）"
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
                    mgr = getattr(self._orchestrator, "_skill_manager", None)
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
                        return format_initializing_ack(pending=pending_count(session_key))
                    return format_initializing_ack()
        except Exception as exc:
            logger.debug("Session initializing skipped: %s", exc)

        if self._should_queue_inbound(session_key, text):
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
                    return format_steer_gateway_reply(accepted=True, active=True)
            elif mode == "interrupt":
                self._interrupt_session_loop(session_key)
            else:
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

        from butler.gateway.reply_admission import release, try_admit

        admission = try_admit(session_key)
        if admission is None:
            from butler.gateway.message_queue import enqueue_inbound, format_queued_ack, pending_count

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
            return "会话处理中，请稍候…"

        logger.info("Gateway enter_session session=%s", session_key)
        session_lock = self._session_registry.enter_session(session_key)
        out = ""
        try:
            out = self._handle_message_locked(
                text,
                session_key=session_key,
                platform=platform,
                external_id=external_id,
            )
            logger.info(
                "Gateway handle_message done session=%s elapsed=%.1fs out_len=%d",
                session_key,
                _time.monotonic() - _t0,
                len(out or ""),
            )
        finally:
            self._session_registry.exit_session(session_key, session_lock)
            release(admission)
            if _idempotency_reserved:
                try:
                    complete_inbound(session_key, inbound_id)
                except Exception as exc:
                    logger.debug("Inbound completion record skipped: %s", exc)
        follow = self._drain_queued_inbound(
            session_key,
            platform=platform,
            external_id=external_id,
            primary_reply=out,
        )
        # follow 非空表示未走 bridge 单独推送（成功时 _drain 返回 ""）
        if follow:
            out = f"{out}\n\n---\n\n{follow}" if out else follow
        return out

    def _handle_message_locked(
        self,
        text: str,
        *,
        session_key: str = "default",
        platform: str = "unknown",
        external_id: str | None = None,
    ) -> str:
        if not text.strip():
            return ""

        welcome_prefix = _maybe_welcome_prefix(session_key)

        for normalizer in (
            _normalize_detail_request,
            _normalize_switch_request,
            _normalize_status_request,
            _normalize_new_session_request,
            _normalize_memo_request,
            _normalize_contacts_request,
            _normalize_expense_request,
            _normalize_habits_request,
        ):
            cmd = normalizer(text)
            if cmd is not None:
                response = self._handle_command(
                    cmd,
                    session_key=session_key,
                    platform=platform,
                    external_id=external_id,
                )
                if response is not None:
                    return response

        if text.startswith("/"):
            response = self._handle_command(
                text,
                session_key=session_key,
                platform=platform,
                external_id=external_id,
            )
            if response is not None:
                return response

        from butler.execution_context import use_execution_context
        from butler.gateway.hooks import apply_pre_llm_context
        from butler.hooks.runner import run_user_prompt_submit_hooks

        import time as _time

        _turn_started = _time.monotonic()
        logger.info(
            "Gateway turn start session=%s platform=%s preview=%r",
            session_key,
            platform,
            text[:80],
        )

        prompt_hooks = run_user_prompt_submit_hooks(
            text.strip(),
            session_key=session_key,
            platform=platform,
        )
        if prompt_hooks.blocked:
            return prompt_hooks.block_message
        if prompt_hooks.prevent_continuation:
            return prompt_hooks.stop_message or "已停止（UserPromptSubmit hook）"

        with use_execution_context(self._orchestrator, session_key=session_key):
            from butler.project.lead import gateway_loop_role

            pm = self._orchestrator.project_manager
            proj_name = pm.resolve_active_project_name(session_key=session_key)
            proj = pm.get_current(session_key=session_key)
            from butler.plan.mode import is_plan_mode

            loop_role = gateway_loop_role(proj_name, project=proj)
            if is_plan_mode(session_key):
                loop_role = "plan"
            health: dict[str, Any] = {
                "session_key": session_key,
                "platform": platform,
                "platform_chat_id": external_id or "",
                "last_user_query": text.strip()[:500],
                "gateway_agent_role": loop_role,
            }
            augmented = apply_pre_llm_context(
                self._orchestrator.inject_skill_context(text, diagnostics=health),
                session_key=session_key,
                orchestrator=self._orchestrator,
            )
            ephemeral_system = None
            ephemeral_parts: list[str] = []
            try:
                from butler.core.intent_keywords import detect_intent_banner

                intent_banner = detect_intent_banner(text)
                if intent_banner:
                    ephemeral_parts.append(intent_banner)
                    health["intent_keyword_banner"] = True
            except Exception as exc:
                logger.debug("Intent keyword detection skipped: %s", exc)
            try:
                from butler.core.mode_classifier import detect_mode_suggestion_banner

                mode_banner = detect_mode_suggestion_banner(text, session_key=session_key)
                if mode_banner:
                    ephemeral_parts.append(mode_banner)
                    health["mode_classifier_banner"] = True
            except Exception as exc:
                logger.debug("Mode classifier detection skipped: %s", exc)
            if ephemeral_parts:
                ephemeral_system = "\n\n".join(ephemeral_parts)
            if prompt_hooks.additional_context:
                hook_ctx = "\n\n".join(prompt_hooks.additional_context)
                augmented = f"{hook_ctx}\n\n{augmented}"

            loop = self._get_or_create_loop(session_key)
            original_loop_config = loop.config
            try:
                from butler.gateway.inbound_validate import validate_loop_messages_before_turn

                seq_err = validate_loop_messages_before_turn(loop.messages)
                if seq_err:
                    return seq_err
            except Exception as exc:
                logger.debug("Loop message validation skipped: %s", exc)
            from butler.core.turn_token_budget import resolve_turn_budget

            loop.config, turn_budget, augmented = resolve_turn_budget(augmented, loop.config)
            if turn_budget:
                health["turn_token_budget"] = turn_budget
                health["turn_max_iterations"] = loop.config.max_iterations

            try:
                try:
                    from butler.core.model_context import resolve_max_output_tokens

                    max_out = resolve_max_output_tokens(
                        self._orchestrator,
                        session_key=session_key,
                        role=loop_role,
                    )
                    hygiene_compressed = loop.hygiene_compress_if_needed(
                        max_output_tokens=max_out,
                    )
                    health["hygiene_compressed"] = hygiene_compressed
                    health.update({
                        k: v for k, v in getattr(loop, "diagnostics", {}).items()
                        if str(k).startswith(("hygiene_", "context_"))
                    })
                except Exception as exc:
                    health["hygiene_error"] = str(exc)
                    logger.warning("Gateway hygiene compression skipped: %s", exc)
                attach_turn_memory_prefetch(
                    loop,
                    self._orchestrator,
                    text,
                    role=loop_role,
                    diagnostics=health,
                )
                run_callbacks = _gateway_run_callbacks()

                def _run_turn(msg: str) -> LoopResult:
                    run_kwargs: dict[str, Any] = {}
                    if ephemeral_system:
                        run_kwargs["ephemeral_system"] = ephemeral_system
                    try:
                        if run_callbacks is not None:
                            return loop.run(
                                msg,
                                run_callbacks=run_callbacks,
                                **run_kwargs,
                            )
                        return loop.run(msg, **run_kwargs)
                    except TypeError:
                        if run_callbacks is not None:
                            return loop.run(msg, run_callbacks=run_callbacks)
                        return loop.run(msg)

                try:
                    from butler.core.todo_continuation import run_with_todo_continuation
                    from butler.core.goal_loop import maybe_run_goal_continuation

                    result = run_with_todo_continuation(
                        loop,
                        augmented,
                        session_key,
                        run_fn=_run_turn,
                        run_callbacks=run_callbacks,
                    )
                    result = maybe_run_goal_continuation(
                        loop,
                        result,
                        session_key,
                        run_fn=_run_turn,
                    )
                except Exception as exc:
                    logger.debug("Todo/goal continuation fallback: %s", exc)
                    result = _run_turn(augmented)
                health["loop"] = dict(getattr(result, "diagnostics", {}) or {})
                if getattr(result, "transition_reason", ""):
                    health["loop_transition_reason"] = result.transition_reason
                if result.status == LoopStatus.INTERRUPTED:
                    try:
                        from butler.core.auto_continue import capture_auto_continue_pending

                        capture_auto_continue_pending(
                            session_key,
                            user_preview=augmented,
                            reason="interrupt",
                            diagnostics=health.get("loop") if isinstance(health.get("loop"), dict) else None,
                        )
                    except Exception as exc:
                        logger.debug("Auto continue capture skipped: %s", exc)
                sync_result = sync_turn_memory(
                    self._orchestrator,
                    text,
                    result.final_response or "",
                    interrupted=result.status == LoopStatus.INTERRUPTED,
                    status=result.status,
                    session_id=session_key,
                )
                health["memory_sync"] = sync_result
                from butler.session.lifecycle import queue_prefetch_after_turn

                queue_prefetch_after_turn(
                    self._orchestrator,
                    text,
                    role=loop_role,
                    session_id=session_key,
                )
                self._session_registry.set_health(session_key, health)
                out = self._format_response(result, platform)
                turn_elapsed = _time.monotonic() - _turn_started
                from butler.gateway.outbound_bridge import get_current_bridge

                br = get_current_bridge()
                if br is not None:
                    br.record_turn_elapsed(turn_elapsed)
                    health["outbound_events"] = br.recent_outbound_events()[-8:]
                try:
                    from butler.gateway.item_event_sink import recent_thread_items

                    items = recent_thread_items(8)
                    if items:
                        health["thread_items"] = items
                except Exception as exc:
                    logger.debug("Thread items collection skipped: %s", exc)
                logger.info(
                    "Gateway turn done session=%s elapsed=%.1fs out_len=%d",
                    session_key,
                    turn_elapsed,
                    len(out or ""),
                )
                if welcome_prefix:
                    out = f"{welcome_prefix}\n\n---\n\n{out}" if out else welcome_prefix
                return out
            except Exception as exc:
                health["error"] = str(exc)
                self._session_registry.set_health(session_key, health)
                logger.error(
                    "Message handling failed session=%s elapsed=%.1fs: %s",
                    session_key,
                    _time.monotonic() - _turn_started,
                    exc,
                    exc_info=True,
                )
                from butler.gateway.user_errors import format_gateway_user_error

                card = None
                try:
                    from butler.gateway.error_cards import format_error_card

                    exc_type = type(exc).__name__
                    if "timeout" in exc_type.lower() or "Timeout" in exc_type:
                        card = format_error_card(
                            "delegate_timeout",
                            role="agent",
                            elapsed=round(_time.monotonic() - _turn_started),
                        )
                    elif "Permission" in exc_type:
                        card = format_error_card(
                            "permission_deny",
                            tool="message_handler",
                            reason=str(exc)[:200],
                        )
                    else:
                        card = format_error_card(
                            "tool_error",
                            tool="message_handler",
                            error=str(exc),
                        )
                except Exception:
                    pass
                return card or format_gateway_user_error(exc)
            finally:
                loop.config = original_loop_config

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

        if cmd in ("/projects", "/项目"):
            from butler.gateway.project_commands import handle_project_onboarding_command

            onboard = handle_project_onboarding_command(
                self._orchestrator,
                cmd,
                arg,
                session_key=session_key,
                platform=platform,
                external_id=external_id,
            )
            if onboard is not None:
                return onboard

            projects = self._orchestrator.project_manager.list_projects()
            if not projects:
                return "暂无项目。"
            current = self._orchestrator.project_manager.resolve_active_project_name(
                session_key=session_key,
            )
            lines = [
                "项目列表（* 当前）",
                "  /项目 新建 <slug> [模板]",
                "  /项目 体检",
                "",
            ]
            for p in sorted(projects, key=lambda x: x.name):
                mark = "* " if p.name == current else "  "
                pack = getattr(p, "pack", "") or ""
                extra = f" pack={pack}" if pack else ""
                lines.append(f"{mark}{p.name} ({p.type}{extra}) — {p.description}")
            return "\n".join(lines)

        if cmd in ("/overview", "/总览"):
            return _build_project_overview(self._orchestrator, session_key)

        if cmd in ("/switch", "/切换"):
            if not arg:
                return "用法: /switch <项目名称>"
            parts = session_key.split(":", 2)
            plat = parts[0] if parts else platform
            cid = parts[1] if len(parts) > 1 else "default"
            pm = self._orchestrator.project_manager
            ok = pm.switch_project_for_chat(platform=plat, chat_id=cid, name=arg)
            if ok:
                new_name = pm.get_project_name_for_chat(platform=plat, chat_id=cid)
                cleared = self._session_registry.reset_sessions_for_chat(
                    platform=plat,
                    chat_id=cid,
                )
                extra = ""
                if cleared:
                    extra = f"\n已重建对话引擎（清理 {len(cleared)} 个旧项目会话）。"
                from butler.project.lead import lead_mode_switch_suffix

                lead_note = lead_mode_switch_suffix(new_name)
                return (
                    f"已切换到项目: {new_name}\n"
                    "（下一条消息起使用新项目工具与 workspace。）"
                    f"{extra}{lead_note}"
                )
            available = pm.list_projects()
            if available:
                names = [p.name for p in available]
                return (
                    f"未找到项目: {arg}\n\n"
                    f"可用项目: {', '.join(names)}\n"
                    "提示: 名称需精确或唯一匹配。"
                )
            return f"未找到项目: {arg}（当前无已注册项目，请先用 /项目 新建 创建）"

        if cmd in ("/presets", "/预设"):
            from butler.provider_presets import format_presets_list

            return format_presets_list()

        if cmd in ("/model", "/模型"):
            from butler.model_resolve import handle_model_command

            proj = self._orchestrator.project_manager.get_current(
                session_key=session_key,
            )
            proj_name = (
                self._orchestrator.project_manager.resolve_active_project_name(
                    session_key=session_key,
                )
                or None
            )
            reply, reset_loop = handle_model_command(
                arg,
                settings=self._orchestrator._settings,
                project=proj,
                project_label=proj_name,
            )
            if reset_loop:
                self._session_registry.reset(session_key)
                _reset_tool_audit_events(session_key)
            return reply

        if cmd in ("/status", "/状态"):
            import os

            from butler.project.lead import gateway_loop_role, is_lead_project
            from butler.project.meta import format_project_meta_lines

            s = self._orchestrator._settings
            pm = self._orchestrator.project_manager
            current = pm.resolve_active_project_name(session_key=session_key) or "(无)"
            proj = pm.get_current(session_key=session_key)
            default_proj = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip() or "(未设置)"
            lines = [
                "Butler 状态",
                f"  管家: {s.butler_name}",
                f"  当前项目: {current}",
                f"  环境默认项目: {default_proj}",
                f"  默认 Provider: {s.default_provider}",
            ]
            if proj is not None:
                lines.append(
                    f"  对话引擎: {'项目 Lead（厂长）' if is_lead_project(proj.name, project=proj) else '管家 Butler'}"
                )
                lines.extend(format_project_meta_lines(proj))
            elif current != "(无)":
                lines.append(
                    f"  对话引擎: {gateway_loop_role(current)}"
                )
            from butler.plan.mode import format_plan_mode_status

            lines.append(f"  {format_plan_mode_status(session_key).replace(chr(10), ' ')}")
            return "\n".join(lines)

        if cmd in ("/会话", "/sessions"):
            from butler.gateway.sessions_commands import handle_sessions_command

            sess_out = handle_sessions_command(
                self._orchestrator,
                arg,
                session_key=session_key,
            )
            if sess_out:
                return sess_out

        if cmd in ("/评价", "/outcome"):
            from butler.gateway.outcome_commands import handle_outcome_command

            outcome = handle_outcome_command(
                self._orchestrator,
                arg,
                session_key=session_key,
            )
            if outcome is not None:
                return outcome

        if cmd in ("/health", "/诊断"):
            return self._format_health_summary(session_key)

        if cmd in ("/循环", "/loop"):
            from butler.core.goal_loop import start_goal_loop

            return start_goal_loop(session_key, arg)

        if cmd in ("/停止循环", "/stoploop"):
            from butler.core.goal_loop import stop_goal_loop

            return stop_goal_loop(session_key)

        if cmd in ("/doctor",):
            from butler.ops.security_audit import format_audit_report, run_security_audit

            workspace = None
            try:
                proj = self._orchestrator.project_manager.get_current(session_key=session_key)
                if proj is not None:
                    from pathlib import Path

                    workspace = Path(proj.workspace)
            except Exception as exc:
                logger.debug("Security audit workspace resolve skipped: %s", exc)
            return format_audit_report(run_security_audit(workspace=workspace))

        if cmd in ("/steer", "/指引"):
            from butler.core.steer import format_steer_gateway_reply, is_run_active, steer

            active = is_run_active(session_key)
            accepted = bool(active and steer(arg, session_key=session_key))
            return format_steer_gateway_reply(accepted=accepted, active=active)

        if cmd == "/queue":
            from butler.gateway.queue_settings import apply_queue_command

            return apply_queue_command(session_key, arg)

        if cmd in ("/确认", "/approve"):
            from butler.human_gate import resolve_human_gate_message

            return resolve_human_gate_message(session_key, "确认") or "当前没有待确认的工作流步骤。"

        if cmd in ("/取消", "/cancel"):
            from butler.human_gate import resolve_human_gate_message

            return resolve_human_gate_message(session_key, "取消") or "当前没有待确认的工作流步骤。"

        if cmd in ("/budget", "/预算"):
            from butler.core.turn_token_budget import parse_token_budget_text

            if arg:
                probe = parse_token_budget_text(f"/budget {arg}")
                if probe:
                    return (
                        f"已识别本轮 token 预算约 {probe:,}。"
                        "请直接发送任务并在句末加 +500k，或写「本轮尽量做完」。"
                    )
            return (
                "用法：在任务句末加 +500k / +2m，或发送「本轮尽量做完」。"
                "也可：/budget 500k（提示预算，与下一条任务一并发送）。"
            )

        if cmd in ("/new", "/新对话"):
            from butler.session.lifecycle import handle_new_session_command

            loop = self._sessions.get(session_key)
            self._session_registry.reset(session_key, skip_finalize=True)
            _reset_tool_audit_events(session_key)
            from butler.report import clear_report_cache

            clear_report_cache(session_key)
            from butler.plan.mode import clear_plan_mode

            clear_plan_mode(session_key)
            try:
                from butler.hooks.telemetry import reset_hook_telemetry
                from butler.gateway.completion_telemetry import reset_completion_telemetry

                reset_hook_telemetry(session_key)
                reset_completion_telemetry(session_key)
                from butler.core.read_state import reset_read_state
                from butler.gateway.message_queue import reset_queue
                from butler.gateway.queue_settings import clear_session_override
                from butler.human_gate import clear_session_gates
                from butler.core.instruction_walkup import reset_instruction_claims

                reset_read_state(session_key)
                reset_queue(session_key)
                clear_session_override(session_key)
                clear_session_gates(session_key)
                reset_instruction_claims(session_key=session_key)
                from butler.core.goal_loop import clear_state as clear_goal_loop
                from butler.core.compaction_checkpoint import clear_checkpoint

                clear_goal_loop(session_key)
                clear_checkpoint(session_key)
            except Exception as exc:
                logger.debug("Session cleanup for new session skipped: %s", exc)
            return handle_new_session_command(self._orchestrator, session_key, loop)

        if cmd in ("/detail", "/详细"):
            from butler.report import get_last_report, format_detail
            from butler.report.format import parse_detail_section

            report = get_last_report(session_key)
            if report:
                return format_detail(report, section=parse_detail_section(arg))
            return "暂无可展示的详细报告。"

        if cmd in ("/plan", "/计划", "/规划"):
            from butler.plan.mode import format_plan_mode_status, set_plan_mode

            arg_l = (arg or "").strip().lower()
            if arg_l in ("off", "exit", "执行", "退出", "关闭"):
                from butler.plan.mode import clear_plan_mode

                clear_plan_mode(session_key)
                self._session_registry.reset(session_key)
                return "已退出规划模式，可以委派与写入。"
            set_plan_mode(session_key, True)
            self._session_registry.reset(session_key)
            return format_plan_mode_status(session_key)

        if cmd in ("/执行", "/exit-plan", "/退出规划"):
            from butler.plan.mode import clear_plan_mode

            clear_plan_mode(session_key)
            self._session_registry.reset(session_key)
            return "已退出规划模式，可以委派与写入。"

        if cmd in ("/todos", "/待办"):
            from butler.core.session_todos import format_session_todos_for_wechat

            return format_session_todos_for_wechat(session_key)

        if cmd in ("/memo", "/备忘"):
            from butler.tools.memo import format_memos_for_wechat

            return format_memos_for_wechat(arg)

        if cmd in ("/contacts", "/通讯录"):
            from butler.tools.contacts import format_contacts_for_wechat

            return format_contacts_for_wechat(arg)

        if cmd in ("/expense", "/记账"):
            from butler.tools.expense import format_expense_for_wechat

            return format_expense_for_wechat(arg)

        if cmd in ("/habits", "/打卡"):
            from butler.tools.habits import format_habits_for_wechat

            return format_habits_for_wechat(arg)

        if cmd in ("/project-todos", "/项目待办"):
            from butler.tools.project_todos import format_project_todos_for_wechat

            proj = self._orchestrator.project_manager.active_project
            if proj and getattr(proj, "workspace", None):
                from pathlib import Path

                return format_project_todos_for_wechat(Path(proj.workspace))
            return "无活跃项目。"

        if cmd in ("/导出", "/export", "/export-session", "/导出会话"):
            from butler.gateway.export_commands import handle_export_session_command

            return handle_export_session_command(
                arg,
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )

        if cmd in ("/回滚", "/transcript-revert", "/revert-transcript"):
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
            from butler.core.transcript_revert import truncate_transcript

            if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
                return owner_required_message()
            keep = 0
            if arg.strip().isdigit():
                keep = int(arg.strip())
            result = truncate_transcript(session_key, keep_last_lines=keep or None)
            if not result.get("ok"):
                return f"Transcript 回滚失败: {result.get('error', '?')}"
            if result.get("skipped"):
                return f"Transcript 无需回滚（当前 {result.get('lines_after', '?')} 行）"
            return (
                f"已截断 transcript：丢弃 {result.get('dropped_lines', 0)} 行，"
                f"保留约 {result.get('lines_after', 0)} 行（不含内存中的对话）。"
            )

        if cmd in ("/fork-transcript", "/transcript-fork", "/分叉"):
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
            from butler.core.transcript_fork import fork_transcript_at_user_message

            if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
                return owner_required_message()
            user_idx = 1
            if arg.strip().isdigit():
                user_idx = max(1, int(arg.strip()))
            result = fork_transcript_at_user_message(
                session_key,
                keep_from_user_index=user_idx,
            )
            if not result.get("ok"):
                err = result.get("error", "?")
                if err == "user_index_not_found":
                    return (
                        f"Fork 失败：未找到第 {user_idx} 条 user 消息"
                        f"（共 {result.get('user_messages_found', 0)} 条 user）。"
                    )
                return f"Transcript fork 失败: {err}"
            if result.get("skipped"):
                return f"Transcript 已在第 {user_idx} 条 user 消息处，无需 fork。"
            return (
                f"已从第 {user_idx} 条 user 消息 fork transcript："
                f"丢弃 {result.get('dropped_lines', 0)} 行，保留约 {result.get('lines_after', 0)} 行。"
            )

        if cmd in ("/记忆提炼", "/transcript-memory", "/extract-transcript-memory"):
            from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
            from butler.memory.transcript_memory_pipeline import (
                extract_memory_from_transcript,
                transcript_memory_enabled,
            )

            if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
                return owner_required_message()
            if not transcript_memory_enabled():
                return (
                    "Transcript 记忆提炼未启用。设置 BUTLER_TRANSCRIPT_MEMORY=1 后重试。"
                )
            project = arg.strip() or os.getenv("BUTLER_DEFAULT_PROJECT", "") or ""
            result = extract_memory_from_transcript(session_key, project_name=project)
            if not result.get("ok"):
                return f"记忆提炼失败: {result.get('error', '?')}"
            if result.get("skipped"):
                return (
                    f"跳过提炼：transcript 消息不足（{result.get('message_count', 0)} 条，需 ≥4）。"
                )
            updates = int(result.get("memory_updates") or 0)
            errs = result.get("errors") or []
            if errs:
                return f"提炼完成：写入 {updates} 条；警告: {'; '.join(errs[:2])}"
            return f"提炼完成：从 transcript 写入 {updates} 条记忆。"

        if cmd in ("/确认安装", "/confirm-install"):
            from butler.gateway.registry_commands import handle_confirm_install_command

            return handle_confirm_install_command(
                arg,
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )

        if cmd in ("/技能", "/skills", "/mcp"):
            from butler.gateway.registry_commands import handle_registry_command

            reg = handle_registry_command(
                cmd,
                arg,
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )
            if reg is not None:
                return reg

        if cmd in ("/config", "/配置"):
            from butler.config_service import (
                config_set,
                format_config_get,
                format_config_list,
            )

            if not arg:
                return format_config_list()
            parts = arg.split(maxsplit=1)
            sub = parts[0].lower()
            sub_arg = parts[1].strip() if len(parts) > 1 else ""
            if sub == "list":
                return format_config_list(sub_arg)
            if sub == "get" and sub_arg:
                return format_config_get(sub_arg)
            if sub == "set":
                kv = sub_arg.split(maxsplit=1)
                if len(kv) == 2:
                    result = config_set(kv[0], kv[1])
                    if result.needs_reset:
                        self._session_registry.reset(session_key)
                    return result.message
                return "用法: /config set <变量名> <值>"
            return format_config_get(arg)

        if cmd in ("/帮助", "/help"):
            from butler.gateway.help_commands import format_help_text

            return format_help_text(arg)

        if cmd in ("/tasks", "/任务"):
            from butler.runtime.task_store import (
                count_running_tasks,
                list_recent_tasks,
                mark_stale_tasks,
                task_stale_minutes,
            )

            stale = mark_stale_tasks(session_key, auto_fail=False)
            rows = list_recent_tasks(session_key, limit=5)
            if not rows:
                return "暂无委派任务记录。"
            lines = [
                "最近委派任务:",
                f"  running: {count_running_tasks(session_key)} · stale 阈值: {task_stale_minutes()} 分钟",
            ]
            if stale:
                lines.append(f"  ⚠ 僵死任务 {len(stale)} 个（发 /诊断 查看详情）")
            for row in rows:
                status = row.get("status") or "?"
                ok = row.get("success")
                mark = "✓" if ok is True else ("✗" if ok is False else "…")
                if row.get("stale"):
                    mark = "⏱"
                child_sk = str(row.get("child_session_key") or "").strip()
                child_hint = f" · {child_sk}" if child_sk else ""
                bg = " [后台]" if row.get("background") else ""
                stale_tag = " [stale]" if row.get("stale") else ""
                lines.append(
                    f"  {mark} {row.get('task_id')} [{status}]{stale_tag}{bg}{child_hint} "
                    f"{(row.get('task_preview') or '')[:60]}"
                )
            return "\n".join(lines)

        if cmd in ("/workflow", "/工作流"):
            from butler.workflows.commands import handle_workflow_command

            return handle_workflow_command(
                self._orchestrator,
                arg,
                session_key=session_key,
                platform=platform,
            )

        from butler.gateway.dev_commands import handle_dev_command

        dev_resp = handle_dev_command(cmd, arg)
        if dev_resp is not None:
            return dev_resp

        from butler.gateway.runtime_commands import handle_runtime_command

        rt_resp = handle_runtime_command(self._orchestrator, cmd, arg)
        if rt_resp is not None:
            return rt_resp

        if cmd in ("/记忆状态", "/memory-status"):
            from butler.gateway.memory_commands import format_memory_status

            return format_memory_status(self._orchestrator, session_key=session_key)

        from butler.gateway.memory_commands import handle_memory_pending_command

        mem_resp = handle_memory_pending_command(self._orchestrator, cmd, arg)
        if mem_resp is not None:
            return mem_resp

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
    _tool_audit_summary,
    _reset_tool_audit_events,
    _maybe_welcome_prefix,
    _build_project_overview,
    _inject_previous_session_summary,
    _on_gateway_session_removed,
    _WELCOMED_SESSIONS,
    _WELCOME_TEXT,
)
