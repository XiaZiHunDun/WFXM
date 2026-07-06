"""Outcome log: pending → resolved + reflection (TradingAgents subset)."""

from __future__ import annotations

import csv
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_OUTCOMES_NAME = "outcomes.tsv"
_FIELDNAMES = (
    "row_id",
    "timestamp",
    "project",
    "subject",
    "status",
    "outcome_value",
    "reflection",
    "hypothesis",
    "source",
    "metric_name",
    "metric_value",
)


def outcome_reflection_enabled() -> bool:
    return bool(env_truthy("BUTLER_OUTCOME_REFLECTION", default=True))


def outcomes_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / _OUTCOMES_NAME


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return [dict(row) for row in csv.DictReader(f, delimiter="\t") if row]
    except OSError as exc:
        logger.warning("outcomes.tsv read failed: %s", exc)
        return []


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    _ensure_parent(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in _FIELDNAMES})


def append_pending(
    workspace: Path,
    *,
    project: str,
    subject: str,
    hypothesis: str = "",
    source: str = "",
    metric_name: str = "",
    metric_value: str = "",
) -> dict[str, str]:
    """Phase A: record pending outcome without LLM."""
    if not outcome_reflection_enabled():
        return {}
    ws = Path(workspace).expanduser().resolve()
    path = outcomes_path(ws)
    row_id = uuid.uuid4().hex[:12]
    row = {
        "row_id": row_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project": str(project or "").strip()[:64],
        "subject": str(subject or "default").strip()[:128],
        "status": "pending",
        "outcome_value": "",
        "reflection": "",
        "hypothesis": str(hypothesis or "").strip()[:500],
        "source": str(source or "").strip()[:64],
        "metric_name": str(metric_name or "").strip()[:64],
        "metric_value": str(metric_value or "").strip()[:32],
    }
    rows = _read_rows(path)
    rows.append(row)
    _write_rows(path, rows)
    return row


def resolve_outcome(
    workspace: Path,
    *,
    row_id: str = "",
    subject: str = "",
    outcome_value: str,
    reflection: str = "",
    project: str = "",
) -> dict[str, str] | None:
    """Phase B: mark pending row resolved with outcome + short reflection."""
    if not outcome_reflection_enabled():
        return None
    ws = Path(workspace).expanduser().resolve()
    path = outcomes_path(ws)
    rows = _read_rows(path)
    target: dict[str, str] | None = None
    rid = str(row_id or "").strip()
    subj = str(subject or "").strip()
    proj = str(project or "").strip()

    for row in reversed(rows):
        if str(row.get("status") or "").lower() != "pending":
            continue
        if rid and str(row.get("row_id") or "") == rid:
            target = row
            break
        if subj and str(row.get("subject") or "") == subj:
            if not proj or str(row.get("project") or "") == proj:
                target = row
                break

    if target is None:
        return None

    target["status"] = "resolved"
    target["outcome_value"] = str(outcome_value or "").strip()[:256]
    ref = str(reflection or "").strip()
    if not ref:
        hyp = str(target.get("hypothesis") or "").strip()
        metric = str(target.get("metric_name") or "").strip()
        val = str(target.get("metric_value") or outcome_value or "").strip()
        ref = _default_reflection(hypothesis=hyp, metric_name=metric, outcome_value=val)
    target["reflection"] = ref[:500]
    target["timestamp"] = datetime.now(timezone.utc).isoformat()
    _write_rows(path, rows)
    return target


def _default_reflection(
    *,
    hypothesis: str,
    metric_name: str,
    outcome_value: str,
) -> str:
    parts = []
    if hypothesis:
        parts.append(f"假设「{hypothesis[:120]}」")
    if metric_name and outcome_value:
        parts.append(f"观测 {metric_name}={outcome_value}")
    if not parts:
        return f"结果已记录: {outcome_value[:80]}"
    return "；".join(parts) + "。"


def list_pending(workspace: Path, *, project: str = "", limit: int = 10) -> list[dict[str, str]]:
    path = outcomes_path(Path(workspace))
    rows = [
        r
        for r in _read_rows(path)
        if str(r.get("status") or "").lower() == "pending"
    ]
    proj = str(project or "").strip()
    if proj:
        rows = [r for r in rows if str(r.get("project") or "") == proj]
    if limit > 0:
        rows = rows[-limit:]
    return rows


def format_context_for_prompt(
    workspace: Path,
    *,
    project: str,
    n_same_full: int = 3,
    n_cross_reflection: int = 2,
) -> str:
    """Inject: same-project full rows + cross-project reflection-only."""
    if not outcome_reflection_enabled():
        return ""
    path = outcomes_path(Path(workspace))
    rows = [r for r in _read_rows(path) if str(r.get("status") or "").lower() == "resolved"]
    if not rows:
        return ""

    proj = str(project or "").strip()
    same = [r for r in rows if str(r.get("project") or "") == proj][-n_same_full:]
    cross = [r for r in rows if str(r.get("project") or "") != proj][-n_cross_reflection:]

    lines = ["## 历史结果与反思（outcome log）"]
    if same:
        lines.append("### 本项目近期结果")
        for r in same:
            lines.append(_format_row_full(r))
    if cross:
        lines.append("### 其他项目反思摘要")
        for r in cross:
            ref = str(r.get("reflection") or "").strip()
            if ref:
                subj = str(r.get("subject") or "")
                lines.append(f"- [{r.get('project')}/{subj}] {ref[:300]}")
    return "\n".join(lines)


def _format_row_full(row: dict[str, str]) -> str:
    subj = str(row.get("subject") or "")
    hyp = str(row.get("hypothesis") or "")
    val = str(row.get("outcome_value") or row.get("metric_value") or "")
    ref = str(row.get("reflection") or "")
    parts = [f"- **{subj}**"]
    if hyp:
        parts.append(f"  假设: {hyp[:200]}")
    if val:
        parts.append(f"  结果: {val}")
    if ref:
        parts.append(f"  反思: {ref[:300]}")
    return "\n".join(parts)


def maybe_store_pending_from_metric(
    workspace: Path,
    *,
    project: str,
    job_id: str,
    metric_name: str,
    metric_value: float,
    hypothesis: str = "",
) -> dict[str, str] | None:
    subject = str(job_id or metric_name or "experiment").strip()[:128]
    return append_pending(
        workspace,
        project=project,
        subject=subject,
        hypothesis=hypothesis or f"job {job_id}",
        source="runtime_metric",
        metric_name=metric_name,
        metric_value=f"{metric_value:.8g}",
    )


def maybe_resolve_previous_pending(
    workspace: Path,
    *,
    project: str,
    subject: str,
    outcome_value: str,
    reflection: str = "",
) -> dict[str, str] | None:
    pending = list_pending(workspace, project=project, limit=50)
    match = None
    for row in pending:
        if str(row.get("subject") or "") == subject:
            match = row
            break
    if match is None:
        return None
    return resolve_outcome(
        workspace,
        row_id=str(match.get("row_id") or ""),
        outcome_value=outcome_value,
        reflection=reflection,
        project=project,
    )


__all__ = [
    "append_pending",
    "format_context_for_prompt",
    "list_pending",
    "maybe_resolve_previous_pending",
    "maybe_store_pending_from_metric",
    "outcome_reflection_enabled",
    "outcomes_path",
    "resolve_outcome",
]
