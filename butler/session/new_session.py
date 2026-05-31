"""New-session boundary: clear, format, snapshot."""

from __future__ import annotations

import logging
from typing import Any

from butler.session.lifecycle import session_experience_tag

logger = logging.getLogger(__name__)


def clear_session_boundary_memory(
    orchestrator: Any,
    session_id: str = "",
) -> dict[str, Any]:
    """Drop ephemeral chat echoes after /new (loop history is already reset)."""
    removed = 0
    tag = session_experience_tag(session_id)
    bm = getattr(orchestrator, "butler_memory", None)
    exp = getattr(bm, "experience", None) if bm is not None else None
    if exp is not None and hasattr(exp, "delete_conversation_for_session"):
        try:
            removed = int(exp.delete_conversation_for_session(tag))
        except Exception as exc:
            logger.debug("Conversation experience purge skipped: %s", exc)
            return {"removed": 0, "error": str(exc)}

    provider = getattr(orchestrator, "memory_provider", None) or getattr(
        orchestrator, "_memory_provider", None
    )
    if provider is not None and hasattr(provider, "clear_turn_buffer"):
        try:
            provider.clear_turn_buffer()
        except Exception as exc:
            logger.debug("Provider turn buffer clear skipped: %s", exc)

    from butler.session.post_session_ops import reset_post_session_watermark

    reset_post_session_watermark(orchestrator, session_id)

    from butler.memory.prefetch_cache import clear_prefetch_cache

    clear_prefetch_cache(session_id)
    try:
        from butler.memory.retrieval_telemetry import clear_last_retrieval

        clear_last_retrieval(session_id)
    except Exception as exc:
        logger.debug("Retrieval telemetry clear skipped: %s", exc)
    try:
        from butler.core.tool_result_storage import (
            reset_inject_once_state,
            reset_replacement_state,
        )

        reset_inject_once_state(session_id)
        reset_replacement_state(session_id)
    except Exception as exc:
        logger.debug("Tool result state reset skipped: %s", exc)
    return {"removed": removed, "session_tag": tag}


def format_new_session_user_message(
    *,
    extract_result: dict[str, Any] | None = None,
    purge_result: dict[str, Any] | None = None,
) -> str:
    """User-facing copy for /new and /新对话 (CLI + WeChat)."""
    lines = [
        "已清空本轮对话上下文。",
        "长期记忆（Owner 画像、项目 MEMORY、经验库）仍保留；上轮闲聊回声已移除。",
    ]
    extra = format_session_end_summary(extract_result)
    if extra:
        lines.append(extra.strip())
    removed = int((purge_result or {}).get("removed") or 0)
    if removed > 0:
        lines.append(f"（已清理 {removed} 条会话回声）")
    return "\n".join(lines)


def handle_new_session_command(
    orchestrator: Any,
    session_id: str,
    agent_loop: Any | None,
) -> str:
    """Post-session extract, purge ephemeral echoes, return user message."""
    from butler.session.post_session_ops import trigger_session_end

    extract_result = trigger_session_end(
        orchestrator, agent_loop, session_id=session_id, reason="clear"
    )
    purge_result = clear_session_boundary_memory(orchestrator, session_id)
    try:
        from butler.hooks.runner import run_session_start_hooks

        run_session_start_hooks(source="clear")
    except Exception as exc:
        logger.debug("SessionStart hooks skipped: %s", exc)
    return format_new_session_user_message(
        extract_result=extract_result,
        purge_result=purge_result,
    )


def write_session_summary_snapshot(
    orchestrator: Any,
    agent_loop: Any | None,
    *,
    extract_result: dict[str, Any] | None = None,
    session_id: str = "",
) -> None:
    """Structured session summary for recall (claude-mem subset)."""
    from butler.env_parse import env_truthy

    if not env_truthy("BUTLER_SESSION_SUMMARY", default=True):
        return
    proj = orchestrator.project_manager.get_current(session_key=session_id)
    if proj is None:
        return
    from pathlib import Path
    import json

    turns = 0
    if agent_loop and hasattr(agent_loop, "messages"):
        turns = sum(
            1 for m in agent_loop.messages if isinstance(m, dict) and m.get("role") == "user"
        )
    payload = {
        "session_id": str(session_id or ""),
        "project": str(proj.name or ""),
        "turns": turns,
        "memory_updates": int((extract_result or {}).get("memory_updates") or 0),
        "skills_extracted": int((extract_result or {}).get("skills_extracted") or 0),
        "persona": list((extract_result or {}).get("persona") or []),
        "preference": list((extract_result or {}).get("preference") or []),
        "experience": list((extract_result or {}).get("experience") or []),
    }
    path = Path(proj.workspace) / ".butler" / "session_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    except OSError as exc:
        logger.debug("session_summary.json write skipped: %s", exc)


def format_session_end_summary(result: dict[str, Any] | None) -> str:
    """Human-readable WeChat line after post-session extraction on /new."""
    if not result:
        return ""
    if result.get("skipped"):
        reason = str(result.get("reason") or "")
        if reason == "short_history":
            return "（对话过短，未做长期记忆提炼）"
        if reason == "no_agent_loop":
            return ""
        if reason == "error":
            return "（记忆提炼失败，详见网关日志）"
        return ""
    memory_updates = int(result.get("memory_updates") or 0)
    skills = int(result.get("skills_extracted") or 0)
    parts: list[str] = []
    if memory_updates:
        parts.append(f"长期记忆 +{memory_updates} 条")
    if skills:
        parts.append(f"技能 +{skills} 个")
    if parts:
        return "已提炼：" + "，".join(parts) + "。"
    return "（本轮无可写入的长期记忆）"
