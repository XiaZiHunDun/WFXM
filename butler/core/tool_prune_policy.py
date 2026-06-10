"""Per-tool micro-prune limits (Claude Code microCompact-style tiers)."""

from __future__ import annotations

from butler.core.tool_result_storage import is_persisted_tool_result

CLEARED_TOOL_RESULT_MESSAGE = "[旧工具结果已清空]"

# Read/search/terminal outputs are safe to clear when stale.
_COMPACTABLE = frozenset({
    "read_file",
    "grep",
    "search_files",
    "glob",
    "list_dir",
    "terminal",
    "run_terminal_cmd",
    "run_command",
    "execute_command",
    "web_search",
    "web_fetch",
})

# PIM read/list tools return personal data — aggressive prune + faster clear.
_PIM_SENSITIVE = frozenset({
    "contact_find", "contact_list",
    "memo_list", "memo_search",
    "expense_list", "expense_summary", "expense_search",
    "habit_list", "habit_stats",
    "list_reminders", "reminder_list_active",
})

# Writes and delegation reports keep a longer inline summary.
_PRESERVE = frozenset({
    "write_file",
    "patch",
    "edit_file",
    "apply_patch",
    "delegate_task",
    "run_workflow",
    "run_runtime_job",
})


def _tool_prune_settings():
    from butler.context_settings import resolve_context_config

    return resolve_context_config().tool_prune


def keep_recent_tool_messages() -> int:
    return _tool_prune_settings().keep_recent


def keep_recent_pim_tool_messages() -> int:
    return _tool_prune_settings().pim_keep_recent


def prune_limit_chars(policy: str) -> int:
    tp = _tool_prune_settings()
    if policy == "pii_clearable":
        return tp.pii_chars
    if policy == "clearable":
        return tp.clearable_chars
    if policy == "preserve":
        return tp.preserve_chars
    return tp.default_chars


def classify_tool(tool_name: str) -> str:
    """Return ``pii_clearable`` | ``clearable`` | ``preserve`` | ``default``."""
    name = str(tool_name or "").strip().lower()
    if name in _PIM_SENSITIVE:
        return "pii_clearable"
    if name in _COMPACTABLE:
        return "clearable"
    if name in _PRESERVE:
        return "preserve"
    for prefix in ("read_", "search_", "grep"):
        if name.startswith(prefix):
            return "clearable"
    for prefix in ("write_", "edit_", "patch"):
        if name.startswith(prefix):
            return "preserve"
    return "default"


def build_tool_name_index(messages: list[dict]) -> dict[str, str]:
    """Map tool_call_id → tool name from assistant tool_calls blocks."""
    out: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            if not tid:
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            out[tid] = str(fn.get("name") or "").strip()
    return out


def _tool_message_indices(messages: list[dict]) -> list[int]:
    return [i for i, m in enumerate(messages) if m.get("role") == "tool"]


def prune_tool_message_content(
    content: str,
    *,
    tool_name: str,
    is_stale: bool,
) -> str:
    if is_persisted_tool_result(content):
        return content
    policy = classify_tool(tool_name)
    if policy == "pii_clearable" and is_stale:
        return CLEARED_TOOL_RESULT_MESSAGE
    if policy == "clearable" and is_stale:
        return CLEARED_TOOL_RESULT_MESSAGE
    limit = prune_limit_chars(policy)
    if len(content) <= limit:
        return content
    preview = content[: min(300, limit)].replace("\n", " ")
    return f"[Tool output pruned: {len(content)} chars] {preview}..."
