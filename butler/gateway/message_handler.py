"""Butler Gateway Message Handler.

Processes incoming messages from any platform (WeChat, Telegram, etc.)
through Butler's orchestration layer. Provides the bridge between
external gateways and Butler's AgentLoop.

Information flow:
  User -> Platform Adapter -> Butler Handler -> AgentLoop -> Report Pipeline -> User
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from butler.orchestrator import ButlerOrchestrator
from butler.core.agent_loop import AgentLoop, LoopCallbacks, LoopConfig, LoopResult, LoopStatus
from butler.session_lifecycle import attach_turn_memory_prefetch, sync_turn_memory
from butler.tools.registry import get_tool_definitions, dispatch_tool
from butler.report import AgentReport, format_for_wechat, format_for_cli, cache_report

logger = logging.getLogger(__name__)


class ButlerMessageHandler:
    """Handles messages from any platform through Butler's pipeline.

    The handler maintains per-session AgentLoop instances and routes
    messages through Butler's orchestration layer.
    """

    def __init__(self, channel: str = "gateway"):
        self.channel = channel
        self._orchestrator = ButlerOrchestrator(user_id="owner", channel=channel)
        self._sessions: dict[str, AgentLoop] = {}

    def _get_or_create_loop(self, session_key: str) -> AgentLoop:
        if session_key not in self._sessions:
            self._sessions[session_key] = self._orchestrator.create_agent_loop(
                role="butler",
                tools=get_tool_definitions(),
                tool_dispatcher=dispatch_tool,
            )
        return self._sessions[session_key]

    def handle_message(
        self,
        text: str,
        *,
        session_key: str = "default",
        platform: str = "unknown",
    ) -> str:
        """Process an incoming message and return the response.

        This is the main entry point for all platform messages.
        Returns formatted text appropriate for the platform.
        """
        if not text.strip():
            return ""

        from butler.gateway.hooks import apply_pre_gateway_dispatch
        rewritten = apply_pre_gateway_dispatch(text, session_key=session_key, platform=platform)
        if rewritten is not None:
            if not rewritten.strip():
                return ""
            text = rewritten

        if text.startswith("/"):
            response = self._handle_command(text)
            if response is not None:
                return response

        from butler.gateway.hooks import apply_pre_llm_context
        augmented = apply_pre_llm_context(
            self._orchestrator.inject_skill_context(text),
            session_key=session_key,
        )

        loop = self._get_or_create_loop(session_key)

        try:
            try:
                loop.hygiene_compress_if_needed()
            except Exception as exc:
                logger.warning("Gateway hygiene compression skipped: %s", exc)
            attach_turn_memory_prefetch(loop, self._orchestrator, text, role="butler")
            result = loop.run(augmented)
            sync_turn_memory(
                self._orchestrator,
                text,
                result.final_response or "",
                interrupted=result.status == LoopStatus.INTERRUPTED,
                status=result.status,
                session_id=session_key,
            )
            return self._format_response(result, platform)
        except Exception as exc:
            logger.error("Message handling failed: %s", exc)
            return f"处理失败: {exc}"

    def _handle_command(self, text: str) -> Optional[str]:
        """Handle Butler slash commands. Returns response or None."""
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/projects", "/项目"):
            projects = self._orchestrator.project_manager.list_projects()
            if not projects:
                return "暂无项目。"
            current = self._orchestrator.project_manager.current_project
            lines = []
            for p in sorted(projects, key=lambda x: x.name):
                mark = "* " if p.name == current else "  "
                lines.append(f"{mark}{p.name} ({p.type}) — {p.description}")
            return "\n".join(lines)

        if cmd in ("/switch", "/切换"):
            if not arg:
                return "用法: /switch <项目名称>"
            ok = self._orchestrator.project_manager.switch_project(arg)
            if ok:
                self._sessions.clear()
                return f"已切换到项目: {self._orchestrator.project_manager.current_project}"
            return f"未找到项目: {arg}"

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
                self._sessions.clear()
                return f"已设置 {role_name} → {model_spec}"
            return "用法: /model <角色> <provider/model>"

        if cmd in ("/status", "/状态"):
            s = self._orchestrator._settings
            current = self._orchestrator.project_manager.current_project or "(无)"
            return (
                f"Butler 状态\n"
                f"  管家: {s.butler_name}\n"
                f"  当前项目: {current}\n"
                f"  默认 Provider: {s.default_provider}"
            )

        if cmd in ("/new", "/新对话"):
            from butler.session_lifecycle import trigger_session_end
            for loop in self._sessions.values():
                trigger_session_end(self._orchestrator, loop)
            self._sessions.clear()
            return "已清空对话历史。"

        if cmd in ("/detail", "/详细"):
            from butler.report import get_last_report, format_detail
            report = get_last_report()
            if report:
                return format_detail(report)
            return "暂无可展示的详细报告。"

        return None

    def _format_response(self, result: LoopResult, platform: str) -> str:
        """Format the response appropriately for the platform."""
        if not result.final_response:
            return "（执行完成，无文字输出）"

        if platform in ("wechat", "weixin"):
            text = result.final_response
            if len(text) > 2000:
                text = text[:1997] + "..."
            return text

        return result.final_response
