"""Tool preview and completion lines for the Butler CLI."""

from __future__ import annotations

import json
import os
from difflib import unified_diff
from pathlib import Path

TOOL_EMOJI: dict[str, str] = {
    "read_file": "📖",
    "write_file": "✍️",
    "patch": "🔧",
    "terminal": "💻",
    "search_files": "🔎",
    "list_directory": "📁",
    "delegate_task": "🤖",
    "skills_list": "📚",
    "skill_view": "📚",
}

_PREFIX = "┊"


def _oneline(text: str) -> str:
    return " ".join(str(text).split())


def _trunc(text: str, n: int = 42) -> str:
    text = _oneline(text)
    return text if len(text) <= n else text[: n - 3] + "..."


def _short_path(path: str, n: int = 35) -> str:
    p = _oneline(path)
    return p if len(p) <= n else "..." + p[-(n - 3) :]


def build_tool_preview(tool_name: str, args: dict, *, max_len: int = 60) -> str | None:
    """One-line preview of the primary tool argument."""
    if not args:
        return None
    key_map = {
        "terminal": "command",
        "read_file": "path",
        "write_file": "path",
        "patch": "path",
        "search_files": "pattern",
        "list_directory": "path",
        "skill_view": "name",
        "skills_list": "category",
        "delegate_task": "task",
    }
    key = key_map.get(tool_name)
    if not key or key not in args:
        if tool_name == "delegate_task":
            role = args.get("role", "?")
            return f"→ {role}"
        return None
    value = args[key]
    if tool_name == "delegate_task":
        return f"→ {args.get('role', '?')}: {_trunc(str(value), max_len - 8)}"
    preview = _trunc(str(value), max_len)
    return preview


def tool_failure_hint(result: str | None) -> tuple[bool, str]:
    """Detect failed tool JSON results."""
    if not result:
        return False, ""
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return "error" in result.lower(), ""
    if data.get("error"):
        err = str(data["error"])[:40]
        return True, f" [red]{err}[/red]"
    exit_code = data.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return True, f" [red]exit {exit_code}[/red]"
    if data.get("success") is False:
        return True, " [red]failed[/red]"
    return False, ""


def format_tool_complete(
    tool_name: str,
    args: dict,
    duration: float,
    result: str | None = None,
) -> str:
    """Rich-markup completion line: ┊ emoji verb detail 1.2s"""
    dur = f"{duration:.1f}s"
    emoji = TOOL_EMOJI.get(tool_name, "⚡")
    failed, suffix = tool_failure_hint(result)
    preview = build_tool_preview(tool_name, args) or tool_name

    if tool_name == "terminal":
        line = f"{_PREFIX} {emoji} $         {_trunc(args.get('command', ''), 42)}  {dur}"
    elif tool_name == "read_file":
        line = f"{_PREFIX} {emoji} read      {_short_path(args.get('path', ''))}  {dur}"
    elif tool_name == "write_file":
        line = f"{_PREFIX} {emoji} write     {_short_path(args.get('path', ''))}  {dur}"
    elif tool_name == "patch":
        line = f"{_PREFIX} {emoji} patch     {_short_path(args.get('path', ''))}  {dur}"
    elif tool_name == "search_files":
        line = f"{_PREFIX} {emoji} grep      {_trunc(args.get('pattern', ''), 35)}  {dur}"
    elif tool_name == "list_directory":
        line = f"{_PREFIX} {emoji} list      {_short_path(args.get('path', '.'))}  {dur}"
    elif tool_name == "delegate_task":
        line = f"{_PREFIX} {emoji} delegate  → {args.get('role', '?')}  {dur}"
    elif tool_name in ("skills_list", "skill_view"):
        line = f"{_PREFIX} {emoji} skill     {_trunc(preview, 40)}  {dur}"
    else:
        line = f"{_PREFIX} {emoji} {tool_name:9} {_trunc(preview, 40)}  {dur}"

    if failed:
        line += suffix
    return f"  [dim]{line}[/dim]"


def format_tool_start(tool_name: str, args: dict) -> str:
    """Dim line while a tool is running."""
    preview = build_tool_preview(tool_name, args)
    emoji = TOOL_EMOJI.get(tool_name, "⚡")
    detail = f" {preview}" if preview else ""
    return f"  [dim]{_PREFIX} {emoji} {tool_name}{detail}…[/dim]"


def capture_edit_snapshot(tool_name: str, args: dict) -> dict[str, str]:
    """Snapshot file contents before write/patch for inline diff."""
    if tool_name not in ("write_file", "patch"):
        return {}
    path = args.get("path")
    if not path:
        return {}
    p = Path(os.path.expanduser(str(path)))
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        before = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        before = ""
    return {str(p): before}


def render_inline_diff(path: str, before: str, *, max_lines: int = 24) -> str | None:
    """Return dim Rich-markup diff block, or None if empty."""
    p = Path(path)
    try:
        after = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if before == after:
        return None
    try:
        rel = str(p.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        rel = str(p)
    lines = list(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=2,
        )
    )
    if not lines:
        return None
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["... (diff truncated)\n"]
    styled: list[str] = []
    for line in lines:
        text = line.rstrip("\n")
        if text.startswith("+++") or text.startswith("---") or text.startswith("@@"):
            styled.append(f"[dim]{text}[/dim]")
        elif text.startswith("+"):
            styled.append(f"[green]{text}[/green]")
        elif text.startswith("-"):
            styled.append(f"[red]{text}[/red]")
        else:
            styled.append(f"[dim]{text}[/dim]")
    body = "\n".join(styled)
    return f"  {body}"
