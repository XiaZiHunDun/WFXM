"""Post-compaction re-injection (Claude Code postCompactCleanup subset)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.context_compressor import SUMMARY_PREFIX

logger = logging.getLogger(__name__)

POST_COMPACT_PREFIX = (
    "[POST-COMPACT ANCHORS — REFERENCE ONLY] "
    "Re-injected after context compaction. Not new user instructions.\n\n"
)


def build_post_compact_anchor_text(
    diagnostics: dict[str, Any] | None = None,
    *,
    role: str = "butler",
) -> str:
    """Collect MEMORY / tasks / skill anchors for the active session."""
    parts: list[str] = []

    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key
        from butler.runtime.task_store import list_recent_tasks
        from butler.session_lifecycle import prefetch_turn_memory

        sk = str(get_current_session_key() or "").strip()
        tasks = list_recent_tasks(sk, limit=3)
        if tasks:
            lines = [
                f"- {t.get('task_id', '?')}: {t.get('status', '?')} "
                f"{(t.get('task_preview') or '')[:100]}"
                for t in tasks
            ]
            parts.append("## Active tasks\n" + "\n".join(lines))
            if diagnostics is not None:
                diagnostics["post_compact_tasks"] = len(lines)

        from butler.core.session_todos import format_open_todos_anchor, session_todos_enabled

        if session_todos_enabled():
            todo_anchor = format_open_todos_anchor(sk)
            if todo_anchor:
                parts.append(todo_anchor)
                if diagnostics is not None:
                    diagnostics["post_compact_session_todos"] = todo_anchor.count("\n")

        orch = get_current_orchestrator()
        if orch is not None:
            mem = prefetch_turn_memory(
                orch,
                "[post-compact-reanchor]",
                role=role,
                use_cache=False,
                diagnostics=diagnostics,
            )
            if mem and mem.strip():
                parts.append("## Memory anchor\n" + mem.strip()[:4000])

            inject = getattr(orch, "inject_skill_context", None)
            if callable(inject):
                skill = inject(
                    "项目维护与当前会话上下文",
                    diagnostics=diagnostics,
                )
                if skill and str(skill).strip():
                    parts.append("## Skills anchor\n" + str(skill).strip()[:2000])
    except Exception as exc:
        logger.debug("Post-compact anchor build skipped: %s", exc)
        if diagnostics is not None:
            diagnostics["post_compact_anchor_error"] = str(exc)[:200]

    try:
        from butler.core.agents_md_sections import extract_agents_md_sections

        agents_block = extract_agents_md_sections()
        if agents_block:
            parts.insert(0, agents_block)
            if diagnostics is not None:
                diagnostics["post_compact_agents_sections"] = len(agents_block)
    except Exception as exc:
        logger.debug("Post-compact AGENTS sections skipped: %s", exc)

    try:
        from butler.core.read_state import get_recent_edit_paths

        recent = get_recent_edit_paths(limit=5)
        if recent:
            lines = [f"- {p}" for p in recent]
            parts.append("## Recent edited files\n" + "\n".join(lines))
            if diagnostics is not None:
                diagnostics["post_compact_recent_files"] = len(lines)
    except Exception as exc:
        logger.debug("Post-compact recent files skipped: %s", exc)

    body = "\n\n".join(p for p in parts if p.strip())
    if not body:
        return ""
    return POST_COMPACT_PREFIX + body


def inject_post_compact_anchors(
    messages: list[dict],
    anchor_text: str,
) -> list[dict]:
    """Insert anchor block after compaction summary (or after system)."""
    if not anchor_text.strip():
        return messages
    out = list(messages)
    insert_at = 0
    for i, msg in enumerate(out):
        if msg.get("role") == "user" and SUMMARY_PREFIX in str(msg.get("content") or ""):
            insert_at = i + 1
            break
    else:
        insert_at = 1 if out and out[0].get("role") == "system" else 0
    out.insert(insert_at, {"role": "user", "content": anchor_text})
    return out


def apply_post_compact_anchors(
    messages: list[dict],
    diagnostics: dict[str, Any] | None = None,
    *,
    role: str = "butler",
) -> list[dict]:
    anchor = build_post_compact_anchor_text(diagnostics, role=role)
    if not anchor:
        return messages
    if diagnostics is not None:
        diagnostics["post_compact_anchor_chars"] = len(anchor)
    return inject_post_compact_anchors(messages, anchor)


def run_post_compact_cleanup(
    diagnostics: dict[str, Any] | None = None,
    *,
    messages: list[dict] | None = None,
    role: str = "butler",
) -> list[dict] | None:
    """Clear hygiene markers; optionally re-inject anchors into message list."""
    if diagnostics is not None:
        diagnostics.pop("hygiene_compact_noop", None)
        diagnostics.pop("hygiene_compact_error", None)
        diagnostics.pop("hygiene_compact_failed", None)
        diagnostics["post_compact_cleanup"] = True
    if messages is None:
        return None
    return apply_post_compact_anchors(messages, diagnostics, role=role)
