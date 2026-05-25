"""TSV experiment ledger under project ``.butler/experiments.tsv``."""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy
from butler.experiments.git_utils import current_git_sha
from butler.experiments.metrics import primary_metric

logger = logging.getLogger(__name__)

_LEDGER_NAME = "experiments.tsv"
_FIELDNAMES = (
    "timestamp",
    "git_sha",
    "metric_name",
    "metric_value",
    "cost_mb",
    "status",
    "hypothesis",
    "job_id",
)


def experiments_ledger_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / _LEDGER_NAME


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            return [dict(row) for row in reader if row]
    except OSError as exc:
        logger.warning("experiments.tsv read failed: %s", exc)
        return []


def append_record(
    workspace: Path,
    *,
    metric_name: str,
    metric_value: float,
    status: str,
    hypothesis: str = "",
    cost_mb: str = "",
    git_sha: str = "",
    job_id: str = "",
    timestamp: str | None = None,
) -> Path:
    """Append one ledger row; returns ledger path."""
    ws = Path(workspace).expanduser().resolve()
    path = experiments_ledger_path(ws)
    _ensure_parent(path)

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    sha = git_sha or current_git_sha(ws)
    st = str(status or "").strip().lower()
    if st not in ("keep", "discard", "crash"):
        st = "keep" if st == "ok" else st or "keep"

    row = {
        "timestamp": ts,
        "git_sha": sha[:40],
        "metric_name": str(metric_name or "score").strip()[:64],
        "metric_value": f"{float(metric_value):.8g}",
        "cost_mb": str(cost_mb or "").strip()[:32],
        "status": st[:16],
        "hypothesis": str(hypothesis or "").strip()[:500],
        "job_id": str(job_id or "").strip()[:64],
    }

    write_header = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, delimiter="\t", extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return path


def list_recent(workspace: Path, *, limit: int = 10) -> list[dict[str, str]]:
    path = experiments_ledger_path(workspace)
    rows = _read_rows(path)
    if limit > 0:
        rows = rows[-limit:]
    return rows


def best_record(
    workspace: Path,
    *,
    metric_name: str = "",
    status: str = "keep",
) -> dict[str, str] | None:
    """Return row with highest metric_value among matching status."""
    want_status = str(status or "keep").strip().lower()
    want_metric = str(metric_name or "").strip().lower()
    best: dict[str, str] | None = None
    best_val: float | None = None
    for row in _read_rows(experiments_ledger_path(workspace)):
        if want_status and str(row.get("status") or "").lower() != want_status:
            continue
        name = str(row.get("metric_name") or "").strip().lower()
        if want_metric and name != want_metric:
            continue
        try:
            val = float(str(row.get("metric_value") or ""))
        except ValueError:
            continue
        if best_val is None or val > best_val:
            best_val = val
            best = row
    return best


def maybe_write_last_run_log(workspace: Path, stdout: str, stderr: str) -> Path | None:
    """Persist long job output for grep (autoresearch hygiene)."""
    lines_out = len((stdout or "").splitlines())
    lines_err = len((stderr or "").splitlines())
    try:
        threshold = max(50, int(os.getenv("BUTLER_EXPERIMENT_LOG_LINES", "200") or "200"))
    except ValueError:
        threshold = 200
    if lines_out < threshold and lines_err < max(20, threshold // 4):
        return None
    ws = Path(workspace).expanduser().resolve()
    path = ws / ".butler" / "last_run.log"
    _ensure_parent(path)
    blob = f"--- stdout ({lines_out} lines) ---\n{stdout}\n\n--- stderr ({lines_err} lines) ---\n{stderr}\n"
    try:
        path.write_text(blob, encoding="utf-8")
    except OSError as exc:
        logger.debug("last_run.log write skipped: %s", exc)
        return None
    return path


def maybe_record_from_job_result(
    workspace: Path,
    job_id: str,
    result: dict[str, Any],
    *,
    hypothesis: str = "",
) -> dict[str, Any] | None:
    """Parse METRIC lines from job stdout; append ledger row on success."""
    if not env_truthy("BUTLER_EXPERIMENT_LEDGER", default=True):
        return None

    ws = Path(workspace).expanduser().resolve()
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    maybe_write_last_run_log(ws, stdout, stderr)

    metric = primary_metric(stdout + "\n" + stderr)
    if metric is None:
        return None

    ok = bool(result.get("success"))
    status = "keep" if ok else "crash"
    hyp = hypothesis or f"runtime job {job_id}"
    path = append_record(
        ws,
        metric_name=str(metric["metric_name"]),
        metric_value=float(metric["metric_value"]),
        status=status,
        hypothesis=hyp,
        job_id=job_id,
    )
    out: dict[str, Any] = {
        "ledger_path": str(path),
        "metric_name": metric["metric_name"],
        "metric_value": metric["metric_value"],
        "status": status,
    }
    try:
        from butler.experiments.outcomes import (
            maybe_resolve_previous_pending,
            maybe_store_pending_from_metric,
        )

        proj_name = ""
        try:
            from butler.project_manager import get_project_manager

            for p in get_project_manager().list_projects():
                if Path(p.workspace).resolve() == ws:
                    proj_name = p.name
                    break
        except Exception:
            pass
        subj = str(job_id or metric["metric_name"])
        maybe_resolve_previous_pending(
            ws,
            project=proj_name,
            subject=subj,
            outcome_value=str(metric["metric_value"]),
        )
        pending_row = maybe_store_pending_from_metric(
            ws,
            project=proj_name,
            job_id=job_id,
            metric_name=str(metric["metric_name"]),
            metric_value=float(metric["metric_value"]),
            hypothesis=hyp,
        )
        if pending_row:
            out["outcome_pending_id"] = pending_row.get("row_id")
    except Exception as exc:
        logger.debug("outcome log hook skipped: %s", exc)
    if status == "crash":
        try:
            from butler.experiments.crash_guard import (
                consecutive_crash_count,
                should_block_experiment_run,
            )

            streak = consecutive_crash_count(ws, hypothesis=hyp, job_id=job_id)
            out["crash_streak"] = streak
            blocked, reason = should_block_experiment_run(ws, hypothesis=hyp, job_id=job_id)
            if blocked:
                out["experiment_blocked"] = True
                out["block_reason"] = reason
        except Exception as exc:
            logger.debug("Experiment crash guard skipped: %s", exc)
    return out


__all__ = [
    "append_record",
    "best_record",
    "experiments_ledger_path",
    "list_recent",
    "maybe_record_from_job_result",
    "maybe_write_last_run_log",
]
