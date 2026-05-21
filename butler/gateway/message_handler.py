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
from butler.core.agent_loop import AgentLoop, LoopCallbacks, LoopConfig, LoopResult, LoopStatus
from butler.session_lifecycle import (
    attach_turn_memory_prefetch,
    clear_session_boundary_memory,
    sync_turn_memory,
)
from butler.tools.registry import dispatch_tool
from butler.tools.project_tools import get_current_project_tools
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
        from butler.tools.project_tools import get_tool_definitions_for_project

        tools = get_tool_definitions_for_project(project, role="butler")
        return self._orchestrator.create_agent_loop(
            role="butler",
            tools=tools,
            tool_dispatcher=dispatch_tool,
        )

    def _finalize_session(self, loop: AgentLoop) -> None:
        from butler.session_lifecycle import trigger_session_end

        trigger_session_end(self._orchestrator, loop)

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
            out = self._handle_message_locked(text, session_key=session_key, platform=platform)
            logger.info(
                "Gateway handle_message done (slash) session=%s elapsed=%.1fs out_len=%d",
                session_key,
                _time.monotonic() - _t0,
                len(out or ""),
            )
            return out

        logger.info("Gateway enter_session session=%s", session_key)
        session_lock = self._session_registry.enter_session(session_key)
        try:
            out = self._handle_message_locked(text, session_key=session_key, platform=platform)
            logger.info(
                "Gateway handle_message done session=%s elapsed=%.1fs out_len=%d",
                session_key,
                _time.monotonic() - _t0,
                len(out or ""),
            )
            return out
        finally:
            self._session_registry.exit_session(session_key, session_lock)

    def _handle_message_locked(
        self,
        text: str,
        *,
        session_key: str = "default",
        platform: str = "unknown",
    ) -> str:
        if not text.strip():
            return ""

        detail_cmd = _normalize_detail_request(text)
        if detail_cmd is not None:
            response = self._handle_command(
                detail_cmd, session_key=session_key, platform=platform
            )
            if response is not None:
                return response

        if text.startswith("/"):
            response = self._handle_command(
                text, session_key=session_key, platform=platform
            )
            if response is not None:
                return response

        from butler.execution_context import use_execution_context
        from butler.gateway.hooks import apply_pre_llm_context

        import time as _time

        _turn_started = _time.monotonic()
        logger.info(
            "Gateway turn start session=%s platform=%s preview=%r",
            session_key,
            platform,
            text[:80],
        )

        with use_execution_context(self._orchestrator, session_key=session_key):
            health: dict[str, Any] = {
                "session_key": session_key,
                "platform": platform,
            }
            augmented = apply_pre_llm_context(
                self._orchestrator.inject_skill_context(text, diagnostics=health),
                session_key=session_key,
            )

            loop = self._get_or_create_loop(session_key)

            try:
                try:
                    hygiene_compressed = loop.hygiene_compress_if_needed()
                    health["hygiene_compressed"] = hygiene_compressed
                    health.update({
                        k: v for k, v in getattr(loop, "diagnostics", {}).items()
                        if str(k).startswith("hygiene_")
                    })
                except Exception as exc:
                    health["hygiene_error"] = str(exc)
                    logger.warning("Gateway hygiene compression skipped: %s", exc)
                attach_turn_memory_prefetch(
                    loop,
                    self._orchestrator,
                    text,
                    role="butler",
                    diagnostics=health,
                )
                run_callbacks = _gateway_run_callbacks()
                if run_callbacks is not None:
                    result = loop.run(augmented, run_callbacks=run_callbacks)
                else:
                    result = loop.run(augmented)
                health["loop"] = dict(getattr(result, "diagnostics", {}) or {})
                sync_result = sync_turn_memory(
                    self._orchestrator,
                    text,
                    result.final_response or "",
                    interrupted=result.status == LoopStatus.INTERRUPTED,
                    status=result.status,
                    session_id=session_key,
                )
                health["memory_sync"] = sync_result
                self._session_registry.set_health(session_key, health)
                out = self._format_response(result, platform)
                logger.info(
                    "Gateway turn done session=%s elapsed=%.1fs out_len=%d",
                    session_key,
                    _time.monotonic() - _turn_started,
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
    ) -> Optional[str]:
        """Handle Butler slash commands. Returns response or None."""
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/projects", "/项目"):
            projects = self._orchestrator.project_manager.list_projects()
            if not projects:
                return "暂无项目。"
            current = self._orchestrator.project_manager.resolve_active_project_name(
                session_key=session_key,
            )
            lines = []
            for p in sorted(projects, key=lambda x: x.name):
                mark = "* " if p.name == current else "  "
                lines.append(f"{mark}{p.name} ({p.type}) — {p.description}")
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
                return (
                    f"已切换到项目: {new_name}\n"
                    "（下一条消息起使用新项目工具与 workspace。）"
                    f"{extra}"
                )
            return f"未找到项目: {arg}（名称需精确或唯一匹配）"

        if cmd in ("/model", "/模型"):
            if not arg:
                from butler.config import get_model_config
                lines = ["当前模型配置:"]
                for role in ("butler", "dev_agent", "content_agent", "review_agent"):
                    mc = get_model_config(role)
                    lines.append(f"  {role}: {mc.provider or '-'}/{mc.model or '-'}")
                return "\n".join(lines)

            role_model = arg.split(maxsplit=1)
            if len(role_model) == 2:
                from butler.config import ModelConfig
                role_name, model_spec = role_model
                pm_parts = model_spec.split("/", 1)
                if len(pm_parts) == 2:
                    cfg = ModelConfig(provider=pm_parts[0], model=pm_parts[1])
                else:
                    cfg = ModelConfig(model=model_spec)
                self._orchestrator._settings.set_runtime_model_override(role_name, cfg)
                self._session_registry.reset(session_key)
                _reset_tool_audit_events(session_key)
                return f"已设置 {role_name} → {model_spec}（已重置当前会话 Loop）"
            return "用法: /model <角色> <provider/model>"

        if cmd in ("/status", "/状态"):
            import os

            s = self._orchestrator._settings
            current = (
                self._orchestrator.project_manager.resolve_active_project_name(
                    session_key=session_key,
                )
                or "(无)"
            )
            default_proj = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip() or "(未设置)"
            return (
                f"Butler 状态\n"
                f"  管家: {s.butler_name}\n"
                f"  当前项目: {current}\n"
                f"  环境默认项目: {default_proj}\n"
                f"  默认 Provider: {s.default_provider}"
            )

        if cmd in ("/health", "/诊断"):
            return self._format_health_summary(session_key)

        if cmd in ("/new", "/新对话"):
            from butler.session_lifecycle import (
                format_session_end_summary,
                trigger_session_end,
            )

            loop = self._sessions.get(session_key)
            extract_result = (
                trigger_session_end(self._orchestrator, loop)
                if loop is not None
                else {"skipped": True, "reason": "no_agent_loop"}
            )
            self._session_registry.reset(session_key, skip_finalize=True)
            _reset_tool_audit_events(session_key)
            clear_session_boundary_memory(self._orchestrator, session_key)
            from butler.report import clear_report_cache

            clear_report_cache(session_key)
            extra = format_session_end_summary(extract_result)
            return "已清空对话历史。" + (f"\n{extra}" if extra else "")

        if cmd in ("/detail", "/详细"):
            from butler.report import get_last_report, format_detail
            from butler.report_format import parse_detail_section

            report = get_last_report(session_key)
            if report:
                return format_detail(report, section=parse_detail_section(arg))
            return "暂无可展示的详细报告。"

        if cmd in ("/workflow", "/工作流"):
            from butler.workflows.commands import handle_workflow_command

            return handle_workflow_command(
                self._orchestrator,
                arg,
                session_key=session_key,
                platform=platform,
            )

        from butler.gateway.memory_commands import handle_memory_pending_command

        mem_resp = handle_memory_pending_command(self._orchestrator, cmd, arg)
        if mem_resp is not None:
            return mem_resp

        return None

    def _format_health_summary(self, session_key: str = "default") -> str:
        health = self.last_health_summary(session_key)
        tool_summary = _tool_audit_summary(session_key)

        from butler.memory.diagnostics import (
            collect_memory_layer_stats,
            format_memory_diagnostic_lines,
        )

        mem_stats = collect_memory_layer_stats(
            self._orchestrator, session_key=session_key
        )
        if health:
            if health.get("memory_prefetch_chars") is not None:
                mem_stats["last_prefetch_chars"] = health.get("memory_prefetch_chars")
            elif health.get("memory_context_chars") is not None:
                mem_stats["last_prefetch_chars"] = health.get("memory_context_chars")

        if not health and not tool_summary["total"]:
            lines = [
                "Butler 诊断",
                f"会话: {session_key}",
                "轮次诊断: 暂无（本会话尚无完整对话轮次）",
            ]
            lines.extend(format_memory_diagnostic_lines(mem_stats))
            return "\n".join(lines)

        if health:
            loop_health = health.get("loop") if isinstance(health.get("loop"), dict) else {}
            memory_sync = health.get("memory_sync") if isinstance(health.get("memory_sync"), dict) else {}

            schema_recovered = bool(
                health.get("schema_recovered") or loop_health.get("schema_recovered")
            )
            schema_keywords = (
                health.get("schema_keywords_stripped")
                or loop_health.get("schema_keywords_stripped")
                or 0
            )
            skill_matches = health.get("skill_matches") or []
            if not isinstance(skill_matches, list):
                skill_matches = [str(skill_matches)]

            from butler.transport.auxiliary_client import resolve_auxiliary_config

            try:
                aux = resolve_auxiliary_config("post_session")
                aux_label = f"{aux.provider or '?'}/{aux.model or '?'}"
            except Exception:
                aux_label = "未配置"

            lines = [
                "Butler 诊断",
                f"会话: {health.get('session_key') or session_key}",
                f"平台: {health.get('platform') or '-'}",
                f"记忆提炼模型(post_session): {aux_label}",
                f"压缩: {'是' if health.get('hygiene_compressed') else '否'}",
                f"Schema 降级: {'是' if schema_recovered else '否'}",
                f"剥离关键字: {schema_keywords}",
                f"Skill: {'已注入' if health.get('skill_context_injected') else '未注入'}",
                f"命中 Skill: {', '.join(str(s) for s in skill_matches) if skill_matches else '-'}",
                f"记忆上下文: {'已注入' if health.get('memory_context_injected') else '未注入'}",
                f"记忆同步: {'已同步' if not memory_sync.get('skipped', True) else '跳过'}",
                f"Provider 同步: {'是' if memory_sync.get('provider_synced') else '否'}",
            ]
            lines.extend(format_memory_diagnostic_lines(mem_stats))
            if health.get("error"):
                lines.append("错误: 有（查看日志）")
            if health.get("hygiene_error"):
                lines.append("压缩错误: 有（查看日志）")
        else:
            lines = [
                "Butler 诊断",
                f"会话: {session_key}",
                "轮次诊断: 暂无（本会话尚无完整对话轮次）",
            ]
            lines.extend(format_memory_diagnostic_lines(mem_stats))

        if tool_summary["total"]:
            lines.extend([
                f"工具调用: {tool_summary['total']}",
                f"工具失败: {tool_summary['failed']}",
                f"工具错误码: {', '.join(tool_summary['codes']) if tool_summary['codes'] else '-'}",
            ])
        return "\n".join(lines)

    def _format_response(self, result: LoopResult, platform: str) -> str:
        """Format the response appropriately for the platform."""
        if platform in ("wechat", "weixin"):
            from butler.report_format import wechat_response_text

            return wechat_response_text(result)

        if not result.final_response:
            return "（执行完成，无文字输出）"
        return result.final_response


def _normalize_detail_request(text: str) -> str | None:
    """Map WeChat-friendly「详细」to ``/详细`` without requiring a slash prefix."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    lower = stripped.lower()
    if lower in {"/详细", "/detail", "详细", "detail", "查看详细", "看详细", "完整报告"}:
        return "/详细"
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


def _is_global_session_command(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return False
    parts = stripped.split(maxsplit=1)
    cmd = parts[0].lower()
    return cmd in {"/switch", "/切换", "/model", "/模型"}


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
        "/new",
        "/新对话",
        "/detail",
        "/详细",
        "/workflow",
        "/工作流",
        "/记忆待审",
        "/pending-memory",
        "/待审记忆",
        "/批准记忆",
        "/approve-memory",
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
