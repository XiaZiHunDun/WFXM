"""Session-scoped tool truth from transcript JSONL (read_file paths, etc.)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def session_tool_index_enabled() -> bool:
    return env_truthy("BUTLER_SESSION_TOOL_INDEX", default=True)


def _parse_args_preview(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_read_path(
    path: str,
    *,
    workspace: Path | None,
) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    if workspace is not None and not p.is_absolute():
        p = (workspace / p).resolve(strict=False)
    else:
        p = p.expanduser().resolve(strict=False)
    if workspace is not None:
        try:
            rel = p.relative_to(workspace.resolve(strict=False))
            return rel.as_posix()
        except ValueError:
            pass
    return p.as_posix()


def _iter_tool_action_rows(session_key: str) -> list[dict[str, Any]]:
    if not session_tool_index_enabled():
        return []
    try:
        from butler.core.session_epoch import load_epoch_transcript_rows
    except Exception as exc:
        logger.debug("session tool index load skipped: %s", exc)
        return []
    rows = load_epoch_transcript_rows(session_key, max_lines=500)
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("type") or "") != "tool_action":
            continue
        tool = str(row.get("tool") or "").strip().lower()
        if tool != "read_file":
            continue
        out.append(row)
    return out


def list_session_read_files(
    session_key: str,
    *,
    workspace: Path | str | None = None,
    sources: tuple[str, ...] = ("loop", "delegate"),
    limit: int = 50,
) -> list[str]:
    """Return deduplicated read_file paths for this session epoch (transcript SSOT)."""
    sk = str(session_key or "").strip()
    if not sk:
        return []
    ws: Path | None = None
    if workspace is not None:
        ws = Path(workspace).expanduser().resolve(strict=False)
    allowed = {s.strip().lower() for s in sources if s.strip()}
    seen: set[str] = set()
    ordered: list[str] = []
    for row in _iter_tool_action_rows(sk):
        source = str(row.get("source") or "loop").strip().lower()
        if allowed and source not in allowed:
            continue
        args = _parse_args_preview(str(row.get("args_preview") or ""))
        path = str(args.get("path") or "").strip()
        if not path:
            continue
        norm = _normalize_read_path(path, workspace=ws)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        ordered.append(norm)
        if len(ordered) >= max(1, int(limit)):
            break
    return ordered


def format_session_read_files_block(
    session_key: str,
    *,
    workspace: Path | str | None = None,
    title: str = "[本轮 read_file 事实 — 仅列以下路径]",
) -> str:
    paths = list_session_read_files(session_key, workspace=workspace)
    if not paths:
        return (
            f"{title}\n"
            "（transcript 中尚无本轮 read_file 记录。）\n"
            "你必须直接回答：本轮尚未 read_file 任何文件；勿查 butler_recall、"
            "勿提「上次会话摘要」或 MEMORY；可建议主公先读文件或发 /本轮已读。"
        )
    lines = [title, "用户问「刚才读过哪些文件」时只列下列路径（含 loop 与 delegate 的 read_file；不含 search_files/枚举/记忆预取）："]
    for i, p in enumerate(paths, 1):
        lines.append(f"{i}. `{p}`")
    return "\n".join(lines)


__all__ = [
    "format_session_read_files_block",
    "list_session_read_files",
    "session_tool_index_enabled",
]
