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
    from butler.core.post_compact_cleanup_ops import should_skip_reanchor_safe

    if should_skip_reanchor_safe(diagnostics):
        if diagnostics is not None:
            diagnostics["post_compact_skipped_mid_turn"] = True
        return messages
    return apply_post_compact_anchors(messages, diagnostics, role=role)


def _collect_dev_session_changes() -> str:
    """Build a session change log from tool audit events (write/patch/terminal/git)."""
    from butler.core.post_compact_cleanup_ops import collect_dev_session_changes_safe

    return collect_dev_session_changes_safe()
