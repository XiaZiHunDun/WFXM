"""Structured compaction summary template (OpenCode compaction.ts subset)."""

from __future__ import annotations

import os

# Mirrors OpenCode SUMMARY_TEMPLATE section order (without <template> wrapper).
IDENTIFIER_PRESERVATION = """
Preserve verbatim when present: URLs, file paths, hostnames, task_id, session_key, child_session_key,
error codes, exit codes, JSON keys, and command lines. Do not paraphrase opaque identifiers.
"""

IN_PROGRESS_RULE = """
For any work not finished in this segment, prefix bullets with exactly `IN-PROGRESS:` (e.g. `- IN-PROGRESS: fix tests`).
Do not mark incomplete work as Done/Resolved. Blocked items may use `BLOCKED:` when applicable.
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
- (use `- IN-PROGRESS: ...` for unfinished work or "(none)")

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


def use_hermes_compaction_template() -> bool:
    flag = os.getenv("BUTLER_COMPACTION_USE_HERMES_TEMPLATE", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


def compaction_preflight_checklist_enabled() -> bool:
    from butler.env_parse import env_truthy

    return env_truthy("BUTLER_COMPACTION_PREFLIGHT_CHECKLIST", default=True)


PREFLIGHT_CHECKLIST_APPENDIX = """
Before you finish the summary, reflect on execution quality (add bullets under ## Remaining Work or ## Blocked when relevant):
- If code or config was changed: were tests, lint, or build commands run or explicitly deferred?
- Any files only partially edited or tool errors left unresolved?
- Permission blocks, plan-mode blocks, or delegate failures still open?
"""

HERMES_SUMMARY_TEMPLATE = """Output exactly the Markdown structure below. Keep every section even when empty.
Use terse bullets. Preserve exact paths, commands, error strings, and identifiers. Do not mention compaction.

## Resolved
- (completed items or "(none)")

## Pending
- (open questions or "(none)")

## Remaining Work
- (ordered next actions — prefix unfinished with `IN-PROGRESS:`)

## Active Task
- (what the assistant should do next)

## Key Facts
- (architecture, paths, decisions, blockers)
"""


def _append_preflight_checklist(body: str) -> str:
    if not compaction_preflight_checklist_enabled():
        return body
    return body.rstrip() + "\n\n" + PREFLIGHT_CHECKLIST_APPENDIX.strip()


def build_compaction_user_prompt(*, transcript: str, previous_summary: str = "") -> str:
    prev_block = (
        f"\n\nPrevious summary to merge and update:\n{previous_summary}"
        if previous_summary
        else ""
    )
    if use_hermes_compaction_template():
        return _append_preflight_checklist(
            "Summarize this conversation segment for handoff to a new context window.\n\n"
            f"{IDENTIFIER_PRESERVATION}\n{IN_PROGRESS_RULE}\n{HERMES_SUMMARY_TEMPLATE}{prev_block}\n\n"
            f"Conversation:\n{transcript}"
        )
    if use_opencode_compaction_template():
        return _append_preflight_checklist(
            "Summarize this conversation segment for handoff to a new context window.\n\n"
            f"{IDENTIFIER_PRESERVATION}\n{IN_PROGRESS_RULE}\n{OPENCODE_SUMMARY_TEMPLATE}{prev_block}\n\n"
            f"Conversation:\n{transcript}"
        )
    return _append_preflight_checklist(
        "Summarize this conversation segment for handoff to a new context window.\n\n"
        f"{IN_PROGRESS_RULE}\n"
        "Use this structure:\n"
        "## Resolved\n- (completed items)\n\n"
        "## Pending\n- (open questions)\n\n"
        "## Active Task\n- (what to do next — most important)\n\n"
        "## Key Facts\n- (architecture, paths, decisions)"
        f"{prev_block}\n\nConversation:\n{transcript}"
    )
