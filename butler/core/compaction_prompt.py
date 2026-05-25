"""Structured compaction summary template (OpenCode compaction.ts subset)."""

from __future__ import annotations

import os

# Mirrors OpenCode SUMMARY_TEMPLATE section order (without <template> wrapper).
IDENTIFIER_PRESERVATION = """
Preserve verbatim when present: URLs, file paths, hostnames, task_id, session_key, child_session_key,
error codes, exit codes, JSON keys, and command lines. Do not paraphrase opaque identifiers.
"""

OPENCODE_SUMMARY_TEMPLATE = """Output exactly the Markdown structure below. Keep every section even when empty. Use terse bullets, not prose. Preserve exact paths, commands, error strings, and identifiers when known. Do not mention compaction.

## Goal
- (single-sentence task summary)

## Constraints & Preferences
- (user constraints, preferences, specs, or "(none)")

## Progress
### Done
- (completed work or "(none)")

### In Progress
- (current work or "(none)")

### Blocked
- (blockers or "(none)")

## Key Decisions
- (decision and why, or "(none)")

## Next Steps
- (ordered next actions or "(none)")

## Critical Context
- (important technical facts, errors, open questions, or "(none)")

## Relevant Files
- (file or directory path: why it matters, or "(none)")
"""


def use_opencode_compaction_template() -> bool:
    flag = os.getenv("BUTLER_COMPACTION_USE_OPENCODE_TEMPLATE", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def build_compaction_user_prompt(*, transcript: str, previous_summary: str = "") -> str:
    prev_block = (
        f"\n\nPrevious summary to merge and update:\n{previous_summary}"
        if previous_summary
        else ""
    )
    if use_opencode_compaction_template():
        return (
            "Summarize this conversation segment for handoff to a new context window.\n\n"
            f"{IDENTIFIER_PRESERVATION}\n{OPENCODE_SUMMARY_TEMPLATE}{prev_block}\n\n"
            f"Conversation:\n{transcript}"
        )
    return (
        "Summarize this conversation segment for handoff to a new context window.\n\n"
        "Use this structure:\n"
        "## Resolved\n- (completed items)\n\n"
        "## Pending\n- (open questions)\n\n"
        "## Active Task\n- (what to do next — most important)\n\n"
        "## Key Facts\n- (architecture, paths, decisions)"
        f"{prev_block}\n\nConversation:\n{transcript}"
    )
