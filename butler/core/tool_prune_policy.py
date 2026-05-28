"""Per-tool micro-prune limits (Claude Code microCompact-style tiers)."""

from __future__ import annotations

import os

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


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def keep_recent_tool_messages() -> int:
    return max(1, _int_env("BUTLER_TOOL_PRUNE_KEEP_RECENT", 4))


def prune_limit_chars(policy: str) -> int:
    if policy == "clearable":
        return max(200, _int_env("BUTLER_TOOL_PRUNE_CLEARABLE_CHARS", 400))
    if policy == "preserve":
        return max(400, _int_env("BUTLER_TOOL_PRUNE_PRESERVE_CHARS", 2400))
    return max(200, _int_env("BUTLER_TOOL_PRUNE_DEFAULT_CHARS", 800))


def classify_tool(tool_name: str) -> str:
    """Return ``clearable`` | ``preserve`` | ``default``."""
    name = str(tool_name or "").strip().lower()
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
    if policy == "clearable" and is_stale:
        return CLEARED_TOOL_RESULT_MESSAGE
    limit = prune_limit_chars(policy)
    if len(content) <= limit:
        return content
    preview = content[: min(300, limit)].replace("\n", " ")
    return f"[Tool output pruned: {len(content)} chars] {preview}..."
