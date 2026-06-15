"""Human-readable tool call narrative from session transcript."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_TOOL_VERBS: dict[str, str] = {
    "read_file": "读取",
    "write_file": "写入",
    "patch": "修改",
    "list_directory": "浏览目录",
    "search_files": "搜索文件",
    "grep": "检索",
    "glob": "匹配文件",
    "delegate_task": "委派",
    "butler_recall": "回忆",
    "butler_remember": "记忆",
    "run_terminal": "执行命令",
    "run_runtime_job": "运行任务",
    "set_reminder": "设定提醒",
}


def _parse_args(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _short_path(path: str, *, max_len: int = 56) -> str:
    p = str(path or "").strip()
    if len(p) <= max_len:
        return p
    return "…" + p[-(max_len - 1) :]


def describe_tool_action(
    tool: str,
    args_preview: str = "",
    *,
    source: str = "",
) -> str:
    """One-line Chinese narrative for a tool_action row."""
    name = str(tool or "?").strip().lower()
    verb = _TOOL_VERBS.get(name, name or "调用")
    args = _parse_args(args_preview)
    detail = ""

    if name == "read_file":
        detail = _short_path(str(args.get("path") or ""))
    elif name in ("write_file", "patch", "list_directory"):
        detail = _short_path(str(args.get("path") or args.get("directory") or ""))
    elif name == "delegate_task":
        role = str(args.get("role") or args.get("agent") or "").strip()
        task = str(args.get("task") or args.get("message") or "")[:40]
        detail = f"{role}：{task}" if role else task
    elif name in ("butler_recall", "butler_remember"):
        detail = str(args.get("query") or args.get("content") or "")[:48]
    elif name == "run_terminal":
        detail = str(args.get("command") or "")[:48]
    elif name == "run_runtime_job":
        detail = str(args.get("job") or args.get("name") or "")[:48]
    elif name == "set_reminder":
        detail = str(args.get("message") or "")[:40]
    elif args:
        first = next(iter(args.values()), "")
        detail = str(first)[:48]

    src = str(source or "").strip().lower()
    src_tag = f"（{src}）" if src and src != "loop" else ""
    if detail:
        return f"{verb} {detail}{src_tag}"
    return f"{verb}{src_tag}"


def format_session_tool_narrative(
    session_key: str,
    *,
    limit: int = 10,
    title: str = "本轮工具叙事（transcript）",
) -> str:
    """Format recent tool_action rows as owner-facing narrative."""
    sk = str(session_key or "").strip()
    if not sk:
        return "无会话键，无法读取工具叙事。"
    try:
        from butler.core.session_epoch import load_epoch_transcript_rows
    except Exception as exc:
        logger.debug("tool narrative load skipped: %s", exc)
        return "无法加载 transcript。"

    rows = load_epoch_transcript_rows(sk, max_lines=200)
    actions = [r for r in rows if str(r.get("type") or "") == "tool_action"]
    if not actions:
        return "本轮尚无工具调用（transcript）。"
    tail = actions[-max(1, int(limit)) :]
    lines = [title, "按时间顺序，最近工具活动："]
    for i, row in enumerate(tail, 1):
        tool = str(row.get("tool") or "?")
        preview = str(row.get("args_preview") or "")
        source = str(row.get("source") or "")
        lines.append(f"{i}. {describe_tool_action(tool, preview, source=source)}")
    lines.append("")
    lines.append("原始参数：/本轮工具 raw")
    return "\n".join(lines)


__all__ = [
    "describe_tool_action",
    "format_session_tool_narrative",
]
