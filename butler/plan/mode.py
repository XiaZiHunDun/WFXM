"""Read-only planning mode with Claude Code–style session plan file exceptions."""

from __future__ import annotations

import re
import threading
from pathlib import PurePosixPath
from typing import Any, cast

from butler.tool_guardrails import MUTATING_TOOLS

PLAN_BLOCKED_TOOLS = frozenset(MUTATING_TOOLS) | frozenset({
    "delegate_task",
    "run_workflow",
    "run_runtime_job",
    "delete_file",
})

_PLAN_WRITABLE_RE = re.compile(
    r"(^|/)(\.butler/plan/|plans/|session[-_]?plan)",
    re.IGNORECASE,
)

_PLAN_BY_SESSION: dict[str, bool] = {}
_LOCK = threading.RLock()


def is_plan_writable_path(path: str) -> bool:
    """Paths allowed to mutate during plan mode (CC: session plan file only)."""
    raw = str(path or "").strip()
    if not raw:
        return False
    norm = raw.replace("\\", "/")
    name = PurePosixPath(norm).name.lower()
    if name in ("plan.md", "session-plan.md", "implementation_plan.md"):
        return True
    if norm.lower().endswith(".plan.md"):
        return True
    return bool(_PLAN_WRITABLE_RE.search(norm))


def _tool_target_path(tool_name: str, args: dict[str, Any]) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("path", "file_path", "file", "target_file"):
        val = args.get(key)
        if val:
            return str(val)
    return ""


def load_plan_mode_system_appendix() -> str:
    from pathlib import Path

    from butler.plan.mode_ops import append_plan_graph_appendix_safe, load_plan_prompt_from_paths

    base = Path(__file__).resolve().parent
    candidates = (
        base / "prompts" / "butler_plan_mode.md",
        base.parent / "prompts" / "butler_plan_mode.md",
    )
    body = load_plan_prompt_from_paths(candidates)
    if not body:
        body = (
            "## 规划模式\n只读探索并写 plan 文件；"
            "禁止 delegate_task、terminal 与业务源码写入。用户 /执行 后退出。"
        )
    return str(append_plan_graph_appendix_safe(body))


def set_plan_mode(session_key: str, enabled: bool) -> None:
    from butler.plan.mode_ops import (
        record_plan_mode_enabled_safe,
        save_plan_mode_flag_safe,
    )

    key = str(session_key or "default").strip() or "default"
    with _LOCK:
        if enabled:
            _PLAN_BY_SESSION[key] = True
        else:
            _PLAN_BY_SESSION.pop(key, None)
    save_plan_mode_flag_safe(key, enabled)
    if enabled:
        record_plan_mode_enabled_safe(key)


def is_plan_mode(session_key: str = "") -> bool:
    from butler.plan.mode_ops import load_plan_mode_flag_safe, resolve_session_key_safe

    key = resolve_session_key_safe(session_key)
    with _LOCK:
        if key in _PLAN_BY_SESSION:
            return bool(_PLAN_BY_SESSION[key])
    enabled = load_plan_mode_flag_safe(key)
    with _LOCK:
        if enabled:
            _PLAN_BY_SESSION[key] = True
    return bool(enabled)


def clear_plan_mode(session_key: str = "") -> None:
    from butler.plan.mode_ops import resolve_session_key_safe

    set_plan_mode(resolve_session_key_safe(session_key), False)


def clear_all_plan_modes() -> None:
    """Reset in-memory plan flags (test isolation; does not touch on-disk store)."""
    with _LOCK:
        _PLAN_BY_SESSION.clear()


def check_plan_mode_block(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> str | None:
    """Return user-facing error message if tool is blocked in plan mode."""
    if not is_plan_mode(session_key):
        return None
    if tool_name not in PLAN_BLOCKED_TOOLS:
        return None
    if tool_name in ("write_file", "patch", "edit_file"):
        target = _tool_target_path(tool_name, args or {})
        if is_plan_writable_path(target):
            return None
    return (
        f"当前为规划模式，工具「{tool_name}」已禁用。"
        "仅可写入 .butler/plan/ 或 *plan.md；发「/执行」退出规划后再委派或改代码。"
    )


def format_plan_mode_status(session_key: str = "") -> str:
    if is_plan_mode(session_key):
        return (
            "规划模式: 已开启（只读 + 可写 plan 文件）。\n"
            "可写: .butler/plan/*、*plan.md、plans/*\n"
            "发「/执行」或「/退出规划」开始执行。"
        )
    return "规划模式: 未开启。发「/计划」或「/规划」进入只读规划。"


__all__ = [
    "PLAN_BLOCKED_TOOLS",
    "check_plan_mode_block",
    "clear_all_plan_modes",
    "clear_plan_mode",
    "format_plan_mode_status",
    "is_plan_mode",
    "is_plan_writable_path",
    "load_plan_mode_system_appendix",
    "set_plan_mode",
]
