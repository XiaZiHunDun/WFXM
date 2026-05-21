"""Enrich runtime job summaries (report paths, audit hints)."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from butler.runtime.schema import JobDef

_REPORT_LINE = re.compile(
    r"^报告:\s*(.+)$",
    re.MULTILINE,
)
_REPORT_DIR_LINE = re.compile(
    r"^报告目录:\s*(.+)$",
    re.MULTILINE,
)

# Relative to project workspace / novel-factory
CONSISTENCY_REPORT_DIR = Path("novel-factory") / "06_意见仓库" / "07_一致性检查"


def _display_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _paths_from_stdout(stdout: str, workspace: Path) -> list[str]:
    found: list[str] = []
    for pattern in (_REPORT_LINE,):
        for match in pattern.finditer(stdout or ""):
            raw = match.group(1).strip().strip("'\"")
            if raw:
                p = Path(raw)
                if not p.is_absolute():
                    p = (workspace / p).resolve()
                if p.exists():
                    found.append(_display_path(workspace, p))
                else:
                    found.append(raw.replace("\\", "/"))
    for match in _REPORT_DIR_LINE.finditer(stdout or ""):
        raw = match.group(1).strip().strip("'\"")
        if raw:
            d = Path(raw)
            if not d.is_absolute():
                d = (workspace / d).resolve()
            if d.is_dir():
                found.append(_display_path(workspace, d) + "/")
            else:
                found.append(raw.replace("\\", "/"))
    return found


def _latest_consistency_reports(
    workspace: Path,
    *,
    max_age_seconds: float = 3600,
    limit: int = 2,
) -> list[str]:
    base = (workspace / CONSISTENCY_REPORT_DIR).resolve()
    if not base.is_dir():
        return []
    now = time.time()
    candidates: list[tuple[float, Path]] = []
    for ext in ("*.md", "*.json"):
        for p in base.glob(ext):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if now - mtime <= max_age_seconds:
                candidates.append((mtime, p))
    candidates.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    for _, p in candidates[:limit]:
        out.append(_display_path(workspace, p))
    return out


def enrich_job_result(
    job: JobDef,
    workspace: Path,
    result: dict[str, Any],
    *,
    run_started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Append report paths to summary when detectable (consistency-weekly, etc.)."""
    ws = Path(workspace).expanduser().resolve()
    stdout = str(result.get("stdout") or "")
    paths = _paths_from_stdout(stdout, ws)

    if job.id == "consistency-weekly" or "consistency" in (job.description or "").lower():
        for p in _latest_consistency_reports(ws):
            if p not in paths:
                paths.append(p)

    if not paths:
        return result

    block = "报告路径:\n" + "\n".join(f"· {p}" for p in paths[:5])
    summary = (result.get("summary") or "").strip()
    if block not in summary:
        result["summary"] = f"{summary}\n\n{block}".strip() if summary else block
    result["report_paths"] = paths
    return result
