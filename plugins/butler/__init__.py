"""Butler orchestration plugin for Hermes.

Registers a ``pre_gateway_dispatch`` hook so that Butler slash commands
(``/projects``, ``/switch``, ``/model``, ``/status``) are handled before
reaching the Hermes agent loop.

Gateway protocol:
    The hook receives a ``MessageEvent`` dataclass (not a dict) and must
    return one of:
      {"action": "skip"}    — drop the message (plugin already replied)
      {"action": "rewrite", "text": "..."}  — replace message text
      {"action": "allow"}   — normal flow
      None                  — normal flow
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BUTLER_SLASH_COMMANDS = {
    "/projects", "/switch", "/model", "/status", "/detail",
    "/项目", "/切换", "/模型", "/状态", "/详细",
}


def _is_butler_command(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return False
    cmd = stripped.split()[0].lower()
    return cmd in _BUTLER_SLASH_COMMANDS


def _extract_text(event: Any) -> str:
    """Extract text from either a MessageEvent dataclass or a dict."""
    if hasattr(event, "text"):
        return getattr(event, "text", "") or ""
    if isinstance(event, dict):
        return event.get("text", "") or event.get("message", "") or ""
    return ""


def _handle_butler_gateway_command(text: str) -> Optional[str]:
    """Process Butler slash commands. Returns response text or None."""
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
        return "暂无可展示的详细报告。"

    return None


def _try_send_reply(gateway: Any, event: Any, text: str) -> bool:
    """Best-effort send a reply through the gateway's active adapter."""
    try:
        source = getattr(event, "source", None)
        if source is None:
            return False

        platform = getattr(source, "platform", None)
        chat_id = getattr(source, "chat_id", None)
        if not platform or not chat_id:
            return False

        adapter = None
        adapters = getattr(gateway, "adapters", {})
        if isinstance(adapters, dict):
            adapter = adapters.get(platform)

        if adapter is None:
            return False

        reply_to = getattr(event, "message_id", None)

        if hasattr(adapter, "send_text"):
            coro = adapter.send_text(chat_id, text, reply_to=reply_to)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(coro)
            except RuntimeError:
                asyncio.run(coro)
            return True
    except Exception as exc:
        logger.warning("Butler plugin: send_reply failed: %s", exc)
    return False


def register(ctx):
    """Register Butler hooks with Hermes plugin system."""

    def pre_gateway_dispatch(**kwargs) -> dict[str, Any] | None:
        """Intercept gateway messages for Butler slash commands.

        Conforms to Hermes gateway hook protocol:
        - Receives keyword args: event, gateway, session_store
        - Returns {"action": "skip"/"rewrite"/"allow"} or None
        """
        event = kwargs.get("event")
        gateway = kwargs.get("gateway")

        if event is None:
            return None

        text = _extract_text(event)
        if not text.strip():
            return None

        if not _is_butler_command(text):
            return None

        response = _handle_butler_gateway_command(text)
        if response is None:
            return None

        if gateway is not None:
            sent = _try_send_reply(gateway, event, response)
            if sent:
                return {"action": "skip", "reason": "butler_command_handled"}

        return {
            "action": "rewrite",
            "text": f"请直接回复以下信息给用户（不要添加任何额外内容）：\n\n{response}",
        }

    try:
        ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
        logger.info("Butler plugin: registered pre_gateway_dispatch hook")
    except Exception as exc:
        logger.warning("Butler plugin: hook registration failed: %s", exc)

    logger.info("Butler orchestration plugin loaded")
