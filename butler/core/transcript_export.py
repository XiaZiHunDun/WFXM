"""Export session transcript JSONL to Markdown (internal audit, not public share)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.core.session_transcript import transcript_enabled, transcript_path


def export_max_lines_default() -> int:
    try:
        return max(50, int(os.getenv("BUTLER_TRANSCRIPT_EXPORT_MAX_LINES", "500")))
    except ValueError:
        return 500


def _safe_segment(value: str) -> str:
    raw = str(value or "").strip() or "_global"
    return re.sub(r"[^a-zA-Z0-9._+-]+", "_", raw)[:80] or "_global"


def load_transcript_rows(session_key: str, *, max_lines: int | None = None) -> list[dict[str, Any]]:
    """Load transcript tail or full file when small."""
    if not transcript_enabled():
        return []
    limit = max_lines if max_lines is not None else export_max_lines_default()
    path = transcript_path(session_key)
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []

    if size <= 2 * 1024 * 1024:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
    else:
        try:
            from butler.core.transcript_index import load_tail_rows

            return load_tail_rows(path, max_lines=limit)
        except Exception:
            lines = []
        if not lines:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
            lines = lines[-limit:]

    out: list[dict[str, Any]] = []
    for ln in lines[-limit:]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _format_row_markdown(row: dict[str, Any]) -> str:
    ts = str(row.get("ts") or "")
    typ = str(row.get("type") or "event")
    lines = [f"### {typ}" + (f" · `{ts}`" if ts else "")]

    if typ == "user":
        preview = str(row.get("content_preview") or "")
        if preview:
            lines.append(f"> {preview}")
    elif typ == "assistant":
        preview = str(row.get("content_preview") or "")
        tc = row.get("tool_calls")
        extra = f" · tool_calls={tc}" if tc else ""
        if preview:
            lines.append(f"> {preview}{extra}")
        elif extra:
            lines.append(f"> _(assistant){extra}")
    elif typ in ("compact_scheduled", "compact_done", "compact_boundary"):
        for key in (
            "source",
            "messages_before",
            "messages_after",
            "tokens_estimated",
            "tokens_after",
            "summary_chars",
        ):
            if key in row:
                lines.append(f"- {key}: {row[key]}")
    elif typ == "compaction_turn":
        for key in (
            "iteration",
            "messages_before",
            "messages_after",
            "tokens_before",
            "tokens_after",
        ):
            if key in row:
                lines.append(f"- {key}: {row[key]}")
    elif typ in ("delegate_started", "delegate_turn_start", "delegate_turn_done"):
        for key in ("task_id", "child_session_key", "role", "success", "parent_session_key"):
            if key in row:
                lines.append(f"- {key}: {row[key]}")
    elif typ == "transcript_revert":
        lines.append(f"- dropped_lines: {row.get('dropped_lines')}")
        lines.append(f"- kept_lines: {row.get('kept_lines')}")
    elif typ == "todo_updated":
        lines.append(f"- count: {row.get('count')}")
    else:
        payload = {
            k: v
            for k, v in row.items()
            if k not in ("type", "ts")
        }
        if payload:
            lines.append(f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```")

    return "\n".join(lines)


def _append_tasks_section(session_key: str, parts: list[str]) -> None:
    try:
        from butler.runtime.task_store import list_recent_tasks

        rows = list_recent_tasks(session_key, limit=10)
    except Exception:
        return
    if not rows:
        return
    parts.append("## 委派任务")
    for row in rows:
        mark = "✓" if row.get("success") is True else ("✗" if row.get("success") is False else "…")
        bg = " [后台]" if row.get("background") else ""
        parts.append(
            f"- {mark} `{row.get('task_id')}` [{row.get('status')}]{bg} "
            f"{(row.get('task_preview') or '')[:100]}"
        )


def _append_report_section(session_key: str, parts: list[str]) -> None:
    try:
        from butler.report import get_last_report

        report = get_last_report(session_key)
    except Exception:
        return
    if report is None:
        return
    parts.append("## 最近报告")
    parts.append(f"**{report.headline}**")
    summary = (report.summary or "").strip()
    if summary:
        parts.append(summary[:4000])


def build_session_markdown(
    session_key: str,
    *,
    max_lines: int | None = None,
    include_tasks: bool = True,
    include_report: bool = True,
) -> str:
    sk = str(session_key or "").strip() or "default"
    rows = load_transcript_rows(sk, max_lines=max_lines)
    now = datetime.now(timezone.utc).isoformat()
    parts = [
        f"# Butler 会话导出",
        "",
        f"- session_key: `{sk}`",
        f"- exported_at: {now}",
        f"- transcript_rows: {len(rows)}",
        "",
    ]
    if not rows:
        parts.append("_（无 transcript 记录或已关闭 BUTLER_SESSION_TRANSCRIPT）_")
    else:
        parts.append("## Transcript")
        for row in rows:
            parts.append(_format_row_markdown(row))
            parts.append("")
    if include_tasks:
        _append_tasks_section(sk, parts)
        parts.append("")
    if include_report:
        _append_report_section(sk, parts)
    return "\n".join(parts).strip() + "\n"


def export_session_markdown(
    session_key: str,
    *,
    max_lines: int | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """
    Write markdown export under ``~/.butler/exports/`` or ``<workspace>/.butler/exports/``.
    Returns {ok, path, lines, ...}.
    """
    if not transcript_enabled():
        return {"ok": False, "error": "BUTLER_SESSION_TRANSCRIPT=0"}

    sk = str(session_key or "").strip()
    if not sk:
        return {"ok": False, "error": "empty_session_key"}

    body = build_session_markdown(sk, max_lines=max_lines)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{_safe_segment(sk)}_{stamp}.md"

    if workspace is not None:
        out_dir = Path(workspace) / ".butler" / "exports"
    else:
        out_dir = get_butler_home() / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name
    try:
        out_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    row_count = body.count("### ")
    return {
        "ok": True,
        "path": str(out_path),
        "bytes": len(body.encode("utf-8")),
        "sections": row_count,
        "session_key": sk,
    }


def resolve_export_workspace(session_key: str = "") -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        sk = str(session_key or get_current_session_key() or "").strip()
        proj = pm.get_current(session_key=sk)
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None
