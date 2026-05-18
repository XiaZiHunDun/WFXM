"""Butler orchestration plugin for Hermes.

Registers hooks so that Hermes gateway traffic passes through Butler's
orchestration layer — project routing, slash commands, and model config.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_BUTLER_SLASH_COMMANDS = {
    "/projects", "/switch", "/model", "/status", "/detail",
    "/项目", "/切换", "/模型", "/状态", "/详细",
}


def _is_butler_command(text: str) -> bool:
    """Check if incoming text is a Butler slash command."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return False
    cmd = stripped.split()[0].lower()
    return cmd in _BUTLER_SLASH_COMMANDS


def _handle_butler_gateway_command(text: str, context: dict[str, Any]) -> str | None:
    """Process Butler slash commands in gateway context.

    Returns response text if handled, None to pass through to Hermes.
    """
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    try:
        from butler.project_manager import get_project_manager
        pm = get_project_manager()
    except Exception as exc:
        logger.warning("Butler plugin: project manager unavailable: %s", exc)
        return None

    if cmd in ("/projects", "/项目"):
        projects = pm.list_projects()
        if not projects:
            return "暂无项目。"
        current = pm.current_project
        lines = []
        for p in sorted(projects, key=lambda x: x.name):
            mark = "* " if p.name == current else "  "
            lines.append(f"{mark}{p.name} ({p.type}) — {p.description}")
        return "\n".join(lines)

    if cmd in ("/switch", "/切换"):
        if not arg:
            return "用法: /switch <项目名称>"
        ok = pm.switch_project(arg)
        if ok:
            return f"已切换到项目: {pm.current_project}"
        return f"未找到项目: {arg}"

    if cmd in ("/model", "/模型"):
        try:
            from butler.config import get_model_config
            if not arg:
                lines = []
                for role in ("butler", "dev_agent", "content_agent", "review_agent"):
                    mc = get_model_config(role)
                    lines.append(f"  {role}: {mc.provider or '-'}/{mc.model or '-'}")
                return "当前模型配置:\n" + "\n".join(lines)

            role_model = arg.split(maxsplit=1)
            if len(role_model) == 2:
                from butler.config import ModelConfig, get_butler_settings
                role_name, model_spec = role_model
                pm_parts = model_spec.split("/", 1)
                if len(pm_parts) == 2:
                    cfg = ModelConfig(provider=pm_parts[0], model=pm_parts[1])
                else:
                    cfg = ModelConfig(model=model_spec)
                get_butler_settings().set_runtime_model_override(role_name, cfg)
                return f"已设置 {role_name} → {model_spec}"
            return "用法: /model <角色> <provider/model>"
        except Exception as exc:
            return f"模型切换失败: {exc}"

    if cmd in ("/status", "/状态"):
        try:
            from butler.config import get_butler_settings
            settings = get_butler_settings()
            current = pm.current_project or "(无)"
            return (
                f"Butler 状态\n"
                f"  管家: {settings.butler_name}\n"
                f"  当前项目: {current}\n"
                f"  默认 Provider: {settings.default_provider}"
            )
        except Exception as exc:
            return f"状态获取失败: {exc}"

    if cmd in ("/detail", "/详细"):
        try:
            from butler.report import format_detail, AgentReport
            return "暂无可展示的详细报告（上一次任务未生成结构化报告）。"
        except Exception:
            return "报告系统不可用。"

    return None


def register(ctx):
    """Register Butler hooks with Hermes plugin system."""

    def pre_gateway_dispatch(event: dict[str, Any]) -> dict[str, Any] | None:
        """Intercept gateway messages for Butler command handling.

        If the message is a Butler slash command, handle it and return
        a synthetic response. Otherwise pass through to normal Hermes flow.
        """
        text = event.get("text", "") or event.get("message", "") or ""
        if not text.strip():
            return None

        if _is_butler_command(text):
            response = _handle_butler_gateway_command(text, event)
            if response is not None:
                event["_butler_response"] = response
                event["_butler_handled"] = True
                return event

        return None

    try:
        ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
        logger.info("Butler plugin: registered pre_gateway_dispatch hook")
    except Exception as exc:
        logger.warning("Butler plugin: hook registration failed: %s", exc)

    logger.info("Butler orchestration plugin loaded")
