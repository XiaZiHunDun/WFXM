"""Post-compaction re-injection (Claude Code postCompactCleanup subset)."""

from __future__ import annotations

from typing import Any

from butler.core.context_compressor import SUMMARY_PREFIX

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
    from butler.core.post_compact_cleanup_ops import (
        agents_md_block_safe,
        build_core_anchors_safe,
        design_md_block_safe,
        dev_changes_block_safe,
        facts_anchor_block_safe,
        recent_files_block_safe,
        simplicity_anchor_safe,
    )

    parts = build_core_anchors_safe(diagnostics, role=role)
    agents_block = agents_md_block_safe(diagnostics)
    if agents_block:
        parts.insert(0, agents_block)
    design_block = design_md_block_safe(diagnostics)
    if design_block:
        parts.insert(0, design_block)
    simplicity = simplicity_anchor_safe(diagnostics)
    if simplicity:
        parts.append(simplicity)
    recent = recent_files_block_safe(diagnostics)
    if recent:
        parts.append(recent)
    dev_changes = dev_changes_block_safe(diagnostics)
    if dev_changes:
        parts.append(dev_changes)
    facts_block = facts_anchor_block_safe(diagnostics)
    if facts_block:
        parts.append(facts_block)

    conversation_anchor = _build_conversation_state_anchor(diagnostics)
    if conversation_anchor:
        parts.insert(0, conversation_anchor)

    body = "\n\n".join(p for p in parts if p.strip())
    if not body:
        return ""
    return POST_COMPACT_PREFIX + body


def _build_conversation_state_anchor(diagnostics: dict[str, Any] | None = None) -> str:
    """Build a compact anchor from conversation state for post-compaction injection."""
    if diagnostics is None:
        return ""
    state_data = diagnostics.get("conversation_state")
    if state_data is None:
        return ""
    parts: list[str] = []

    def _add_field(label: str, value: str, max_len: int = 150) -> None:
        if value:
            parts.append(f"**{label}**: {value[:max_len]}")

    if isinstance(state_data, dict):
        _add_field("对话目标", str(state_data.get("conversation_goal") or "").strip())
        _add_field("当前任务", str(state_data.get("current_task_summary") or "").strip())
        _add_field("当前分支", str(state_data.get("current_branch") or "").strip())
        _add_field("构建状态", str(state_data.get("last_build_status") or "").strip())
        files = state_data.get("files_modified") or []
        if files:
            parts.append(f"**已修改文件**: {', '.join(str(f)[:50] for f in files[:5])}")
        chapters = state_data.get("chapter_summaries") or []
        if chapters:
            for ch in chapters[-2:]:
                summary = str(ch.get("summary", "") or "")[:200]
                parts.append(f"**章节{ch.get('chapter_number','')}**: {summary}")
    elif hasattr(state_data, "to_compact_anchor"):
        anchor = state_data.to_compact_anchor()
        if anchor:
            return anchor
        if hasattr(state_data, "conversation_goal"):
            _add_field("对话目标", str(state_data.conversation_goal).strip())
        if hasattr(state_data, "current_task_summary"):
            _add_field("当前任务", str(state_data.current_task_summary).strip())
        if hasattr(state_data, "current_branch"):
            _add_field("当前分支", str(state_data.current_branch).strip())
        if hasattr(state_data, "last_build_status"):
            _add_field("构建状态", str(state_data.last_build_status).strip())
        if hasattr(state_data, "files_modified"):
            files = getattr(state_data, "files_modified", [])
            if files:
                parts.append(f"**已修改文件**: {', '.join(str(f)[:50] for f in files[:5])}")
        if hasattr(state_data, "chapter_summaries"):
            chapters = getattr(state_data, "chapter_summaries", [])
            for ch in chapters[-2:]:
                summary = str(ch.summary)[:200] if hasattr(ch, "summary") else ""
                parts.append(f"**章节{ch.chapter_number}**: {summary}")
    return "\n".join(parts)


def inject_post_compact_anchors(
    messages: list[dict[str, Any]],
    anchor_text: str,
) -> list[dict[str, Any]]:
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
    messages: list[dict[str, Any]],
    diagnostics: dict[str, Any] | None = None,
    *,
    role: str = "butler",
) -> list[dict[str, Any]]:
    anchor = build_post_compact_anchor_text(diagnostics, role=role)
    if not anchor:
        return messages
    if diagnostics is not None:
        diagnostics["post_compact_anchor_chars"] = len(anchor)
    return inject_post_compact_anchors(messages, anchor)


def run_post_compact_cleanup(
    diagnostics: dict[str, Any] | None = None,
    *,
    messages: list[dict[str, Any]] | None = None,
    role: str = "butler",
) -> list[dict[str, Any]] | None:
    """Clear hygiene markers; optionally re-inject anchors into message list."""
    if diagnostics is not None:
        diagnostics.pop("hygiene_compact_noop", None)
        diagnostics.pop("hygiene_compact_error", None)
        diagnostics.pop("hygiene_compact_failed", None)
        diagnostics["post_compact_cleanup"] = True
    if messages is None:
        return None
    from butler.core.post_compact_cleanup_ops import should_skip_reanchor_safe

    if should_skip_reanchor_safe(diagnostics):
        if diagnostics is not None:
            diagnostics["post_compact_skipped_mid_turn"] = True
        return messages
    return apply_post_compact_anchors(messages, diagnostics, role=role)


def _collect_dev_session_changes() -> str:
    """Build a session change log from tool audit events (write/patch/terminal/git)."""
    from butler.core.post_compact_cleanup_ops import collect_dev_session_changes_safe

    return str(collect_dev_session_changes_safe())
