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
from butler.session_keys import chat_id_from_session_key, normalize_session_key
from butler.core.agent_loop import AgentLoop, LoopCallbacks, LoopResult, LoopStatus
from butler.session_lifecycle import attach_turn_memory_prefetch, sync_turn_memory
from butler.tools.registry import dispatch_tool
from butler.report import AgentReport, format_for_wechat, format_for_cli, cache_report
from butler.gateway.session_registry import GatewaySessionRegistry

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
            on_session_removed=_reset_tool_audit_events,
            max_sessions=_env_int("BUTLER_GATEWAY_MAX_SESSIONS", 128),
            idle_ttl_seconds=_env_float("BUTLER_GATEWAY_SESSION_IDLE_TTL_SECONDS", 3600),
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
        from butler.project_lead import gateway_loop_role
        from butler.tools.project_tools import get_tool_definitions_for_project

        loop_role = gateway_loop_role(proj_name, project=project)
        tools = get_tool_definitions_for_project(project, role=loop_role)
        return self._orchestrator.create_agent_loop(
            role=loop_role,
            tools=tools,
            tool_dispatcher=dispatch_tool,
            session_key=session_key,
        )

    def _finalize_session(self, loop: AgentLoop) -> None:
        from butler.session_lifecycle import trigger_session_end

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

    def _drain_queued_inbound(
        self,
        session_key: str,
        *,
        platform: str,
        external_id: str | None,
        primary_reply: str = "",
    ) -> str:
        import os

        from butler.gateway.message_queue import message_queue_enabled, pop_next

        if not message_queue_enabled():
            return ""
        try:
            max_drain = max(0, int(os.getenv("BUTLER_GATEWAY_QUEUE_DRAIN_PER_TURN", "1") or "1"))
        except ValueError:
            max_drain = 1
        parts: list[str] = []
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
        combined = "\n\n---\n\n".join(parts)
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
        if not text.strip():
            return ""

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

        if self._should_queue_inbound(session_key, text):
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
                return format_queued_ack(pending=pending_count(session_key))

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

        for normalizer in (
            _normalize_detail_request,
            _normalize_switch_request,
            _normalize_status_request,
            _normalize_new_session_request,
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
            from butler.project_lead import gateway_loop_role

            pm = self._orchestrator.project_manager
            proj_name = pm.resolve_active_project_name(session_key=session_key)
            proj = pm.get_current(session_key=session_key)
            loop_role = gateway_loop_role(proj_name, project=proj)
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
            if prompt_hooks.additional_context:
                hook_ctx = "\n\n".join(prompt_hooks.additional_context)
                augmented = f"{hook_ctx}\n\n{augmented}"

            loop = self._get_or_create_loop(session_key)
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
                if run_callbacks is not None:
                    result = loop.run(augmented, run_callbacks=run_callbacks)
                else:
                    result = loop.run(augmented)
                health["loop"] = dict(getattr(result, "diagnostics", {}) or {})
                if getattr(result, "transition_reason", ""):
                    health["loop_transition_reason"] = result.transition_reason
                sync_result = sync_turn_memory(
                    self._orchestrator,
                    text,
                    result.final_response or "",
                    interrupted=result.status == LoopStatus.INTERRUPTED,
                    status=result.status,
                    session_id=session_key,
                )
                health["memory_sync"] = sync_result
                from butler.session_lifecycle import queue_prefetch_after_turn

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
                logger.info(
                    "Gateway turn done session=%s elapsed=%.1fs out_len=%d",
                    session_key,
                    turn_elapsed,
                    len(out or ""),
                )
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

                return format_gateway_user_error(exc)

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
                from butler.project_lead import lead_mode_switch_suffix

                lead_note = lead_mode_switch_suffix(new_name)
                return (
                    f"已切换到项目: {new_name}\n"
                    "（下一条消息起使用新项目工具与 workspace。）"
                    f"{extra}{lead_note}"
                )
            return f"未找到项目: {arg}（名称需精确或唯一匹配）"

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

            from butler.project_lead import gateway_loop_role, is_lead_project
            from butler.project_meta import format_project_meta_lines

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
            from butler.plan_mode import format_plan_mode_status

            lines.append(f"  {format_plan_mode_status(session_key).replace(chr(10), ' ')}")
            return "\n".join(lines)

        if cmd in ("/health", "/诊断"):
            return self._format_health_summary(session_key)

        if cmd in ("/steer", "/指引"):
            from butler.core.steer import format_steer_gateway_reply, is_run_active, steer

            active = is_run_active(session_key)
            accepted = bool(active and steer(arg, session_key=session_key))
            return format_steer_gateway_reply(accepted=accepted, active=active)

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
            from butler.session_lifecycle import handle_new_session_command

            loop = self._sessions.get(session_key)
            self._session_registry.reset(session_key, skip_finalize=True)
            _reset_tool_audit_events(session_key)
            from butler.report import clear_report_cache

            clear_report_cache(session_key)
            from butler.plan_mode import clear_plan_mode

            clear_plan_mode(session_key)
            try:
                from butler.hooks.telemetry import reset_hook_telemetry
                from butler.gateway.completion_telemetry import reset_completion_telemetry

                reset_hook_telemetry(session_key)
                reset_completion_telemetry(session_key)
                from butler.core.read_state import reset_read_state
                from butler.gateway.message_queue import reset_queue

                reset_read_state(session_key)
                reset_queue(session_key)
            except Exception:
                pass
            return handle_new_session_command(self._orchestrator, session_key, loop)

        if cmd in ("/detail", "/详细"):
            from butler.report import get_last_report, format_detail
            from butler.report_format import parse_detail_section

            report = get_last_report(session_key)
            if report:
                return format_detail(report, section=parse_detail_section(arg))
            return "暂无可展示的详细报告。"

        if cmd in ("/plan", "/计划"):
            from butler.plan_mode import format_plan_mode_status, set_plan_mode

            arg_l = (arg or "").strip().lower()
            if arg_l in ("off", "exit", "执行", "退出", "关闭"):
                from butler.plan_mode import clear_plan_mode

                clear_plan_mode(session_key)
                return "已退出规划模式，可以委派与写入。"
            set_plan_mode(session_key, True)
            return format_plan_mode_status(session_key)

        if cmd in ("/执行", "/exit-plan", "/退出规划"):
            from butler.plan_mode import clear_plan_mode

            clear_plan_mode(session_key)
            return "已退出规划模式，可以委派与写入。"

        if cmd in ("/tasks", "/任务"):
            from butler.runtime.task_store import list_recent_tasks

            rows = list_recent_tasks(session_key, limit=5)
            if not rows:
                return "暂无委派任务记录。"
            lines = ["最近委派任务:"]
            for row in rows:
                status = row.get("status") or "?"
                ok = row.get("success")
                mark = "✓" if ok is True else ("✗" if ok is False else "…")
                lines.append(
                    f"  {mark} {row.get('task_id')} [{status}] "
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
            from butler.report_format import wechat_response_text

            return wechat_response_text(result)

        if not result.final_response:
            return "（执行完成，无文字输出）"
        return result.final_response


def _normalize_switch_request(text: str) -> str | None:
    """Map「切换到 <项目>」to ``/切换 <项目>`` (WeChat natural phrasing)."""
    stripped = (text or "").strip().rstrip("。.!！?？")
    _switch_prefixes = ("切换到", "切换至", "切换去", "切换回")
    if stripped.startswith("切换") and not any(
        stripped.startswith(p) for p in _switch_prefixes
    ):
        name = stripped[len("切换") :].strip().rstrip("。.!！?？")
        if name and not name.startswith("/"):
            return f"/切换 {name}"
    for prefix in (
        "切换到",
        "切换至",
        "切换去",
        "切换回",
        "现在切到",
        "现在切回",
        "切到",
        "切回",
        "把项目切回去",
        "把项目切回",
    ):
        if stripped.startswith(prefix):
            name = stripped[len(prefix) :].strip().rstrip("。.!！?？")
            if name:
                return f"/切换 {name}"
    if stripped.startswith("切回去"):
        name = stripped[len("切回去") :].strip().rstrip("。.!！?？")
        if name:
            return f"/切换 {name}"
    return None


def _normalize_status_request(text: str) -> str | None:
    """Map project-status questions to ``/状态``."""
    stripped = (text or "").strip().rstrip("？?").strip()
    purpose_hints = (
        "做什么",
        "干什么",
        "用途",
        "目的",
        "介绍",
        "是干嘛",
        "干啥",
        "干什么用",
        "用来做什么",
        "用来干什么",
    )
    if any(hint in stripped for hint in purpose_hints):
        return None
    if stripped in (
        "当前在哪个项目",
        "当前是什么项目",
        "当前什么项目",
        "现在在哪个项目",
        "现在在什么项目",
        "当前项目是什么",
        "确认一下当前项目",
        "报一下当前项目",
    ):
        return "/状态"
    if any(
        phrase in stripped
        for phrase in ("哪个项目", "什么项目", "当前项目", "现在在哪个")
    ) and any(
        hint in stripped
        for hint in ("当前", "现在", "哪个", "什么", "确认", "报", "我是")
    ):
        if any(
            verb in stripped
            for verb in ("读", "读取", "列出", "写", "删", "委派", "检查", "README", "文件")
        ):
            return None
        return "/状态"
    if any(
        phrase in stripped
        for phrase in ("有哪些项目", "项目列表", "哪些workspace", "几个项目")
    ):
        return "/项目"
    return None


def _normalize_new_session_request(text: str) -> str | None:
    """Allow ``/新对话`` with trailing natural-language hints."""
    stripped = (text or "").strip()
    if stripped == "/新对话" or stripped.startswith("/新对话"):
        return "/新对话"
    return None


def _normalize_detail_request(text: str) -> str | None:
    """Map WeChat-friendly「详细」to ``/详细`` without requiring a slash prefix."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    lower = stripped.lower()
    if "报错" in stripped or "错误信息" in stripped:
        return None
    for marker, cmd in (("/详细", "/详细"), ("/detail", "/detail")):
        idx = lower.find(marker)
        if idx >= 0:
            rest = stripped[idx + len(marker) :].strip().rstrip("，,。.!！?？")
            return f"{cmd} {rest}".strip() if rest else cmd
    detail_aliases = {
        "/详细",
        "/detail",
        "详细",
        "detail",
        "查看详细",
        "看详细",
        "完整报告",
        "详细信息",
        "查看详细信息",
        "看一下详细",
        "看一下详细信息",
        "我要看一下详细信息",
        "看详细信息",
    }
    if lower in detail_aliases or stripped in detail_aliases:
        return "/详细"
    for prefix in ("详细", "详细信息", "看一下详细"):
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            rest = stripped[len(prefix) :].strip()
            if rest.startswith("信息"):
                rest = rest[2:].strip()
            if rest:
                return "/详细 " + rest
    if stripped.startswith("详细 "):
        return "/详细 " + stripped[3:].strip()
    if lower.startswith("detail "):
        return "/detail " + stripped[7:].strip()
    return None


def _gateway_run_callbacks() -> LoopCallbacks | None:
    from butler.gateway.outbound_bridge import get_current_bridge

    bridge = get_current_bridge()
    if bridge is None:
        return None
    return LoopCallbacks(
        on_tool_start=bridge.on_tool_start,
        on_tool_complete=bridge.on_tool_complete,
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _is_sessionless_command(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return False
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    return cmd in {
        "/projects",
        "/项目",
        "/switch",
        "/切换",
        "/model",
        "/模型",
        "/status",
        "/状态",
        "/health",
        "/诊断",
        "/steer",
        "/指引",
        "/new",
        "/新对话",
        "/detail",
        "/详细",
        "/plan",
        "/计划",
        "/执行",
        "/exit-plan",
        "/退出规划",
        "/tasks",
        "/任务",
        "/workflow",
        "/工作流",
        "/定时",
        "/runtime",
        "/定时任务",
        "/运行",
        "/run-job",
        "/运行任务",
        "/批准运行",
        "/approve-run",
        "/批准任务",
        "/记忆待审",
        "/pending-memory",
        "/待审记忆",
        "/记忆图谱",
        "/memory-graph",
        "/三元组",
        "/批准记忆",
        "/approve-memory",
        "/拒绝记忆",
        "/reject-memory",
        "/拒绝",
        "/批准",
        "/开发状态",
        "/dev-status",
        "/开发验收",
        "/dev-smoke",
    }


def _tool_audit_summary(session_key: str) -> dict[str, Any]:
    try:
        from butler.tools.registry import get_tool_audit_events
    except Exception:
        return {"total": 0, "failed": 0, "codes": []}
    events = get_tool_audit_events(limit=50, session_key=session_key)
    failed = [event for event in events if not event.get("ok", False)]
    codes = sorted({str(event.get("code")) for event in failed if event.get("code")})
    return {"total": len(events), "failed": len(failed), "codes": codes}


def _reset_tool_audit_events(session_key: str | None = None) -> None:
    try:
        from butler.tools.registry import reset_tool_audit_events
    except Exception:
        return
    reset_tool_audit_events(session_key)
