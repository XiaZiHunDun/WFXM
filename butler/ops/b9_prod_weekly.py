"""Production delegate quality metrics + weekly B9 prod-shaped LIVE probe."""

from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from butler.ops.b9_harness_audit import _is_b9_row

PROD_FAILURE_BUCKETS: tuple[str, ...] = (
    "verify_fail",
    "verify_failed",
    "patch_wrong",
    "no_test",
    "tool_wrong",
    "delegate_failed",
    "other",
)

_SNAPSHOTS_NAME = "prod_delegate_snapshots.jsonl"


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "delegate_failures.jsonl"


def production_snapshots_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _SNAPSHOTS_NAME


def _norm_failure_reason(raw: str) -> str:
    r = (raw or "").strip().lower()
    if r in ("verify_fail", "verify_failed"):
        return "verify_fail"
    if r in PROD_FAILURE_BUCKETS:
        return r
    return "other"


def is_production_delegate_row(rec: dict[str, Any]) -> bool:
    """Dev delegate failures that are not B9/SWE benchmark rows."""
    role = str(rec.get("role") or "").replace("_agent", "").strip().lower()
    if role and role != "dev":
        return False
    if _is_b9_row(rec):
        return False
    preview = str(rec.get("task_preview") or rec.get("category") or "").lower()
    if "swe-benchmark" in preview or "[category:swe" in preview:
        return False
    return True


def load_production_failure_rows(*, limit: int = 500) -> list[dict[str, Any]]:
    path = _audit_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_production_delegate_row(rec):
            rows.append(rec)
    return rows[-limit:]


def summarize_production_delegate_quality(*, limit: int = 500) -> dict[str, Any]:
    """Aggregate production dev delegate failure taxonomy (excludes B9 benchmark)."""
    rows = load_production_failure_rows(limit=limit)
    by_reason: Counter[str] = Counter()
    for rec in rows:
        by_reason[_norm_failure_reason(str(rec.get("failure_reason") or ""))] += 1
    total = len(rows)
    rates = {
        k: round(by_reason.get(k, 0) / total, 4) if total else 0.0
        for k in ("verify_fail", "patch_wrong", "no_test", "tool_wrong", "other")
    }
    return {
        "production_failures_total": total,
        "by_failure_reason": dict(by_reason),
        "rates": rates,
        "audit_path": str(_audit_path()),
        "window_limit": limit,
    }


def compare_production_delegate_delta(*, keep: int = 2) -> dict[str, Any]:
    path = production_snapshots_path()
    if not path.is_file():
        return {"snapshots": 0}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if len(rows) < 2:
        return {"snapshots": len(rows), "note": "need 2+ snapshots for delta"}
    prev, cur = rows[-2], rows[-1]
    delta: dict[str, Any] = {"snapshots": len(rows)}
    for key in ("verify_fail", "patch_wrong", "no_test", "tool_wrong"):
        delta[f"{key}_rate_delta"] = round(
            float((cur.get("rates") or {}).get(key, 0))
            - float((prev.get("rates") or {}).get(key, 0)),
            4,
        )
    delta["production_failures_total_delta"] = int(
        cur.get("production_failures_total", 0)
    ) - int(prev.get("production_failures_total", 0))
    return delta


def record_production_delegate_snapshot(*, limit: int = 500) -> dict[str, Any]:
    summary = summarize_production_delegate_quality(limit=limit)
    summary["recorded_at"] = time.time()
    path = production_snapshots_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    summary["delta"] = compare_production_delegate_delta()
    return summary


def format_production_delegate_report(summary: dict[str, Any] | None = None) -> str:
    data = summary if summary is not None else summarize_production_delegate_quality()
    lines = [
        "=== Production delegate quality ===",
        f"production_failures_total={data.get('production_failures_total', 0)}",
        f"by_failure_reason={data.get('by_failure_reason', {})}",
        f"rates={data.get('rates', {})}",
    ]
    return "\n".join(lines)


def format_production_delegate_delta(delta: dict[str, Any] | None) -> str:
    if not delta or delta.get("snapshots", 0) < 2:
        return "prod_delta=(insufficient snapshots)"
    parts = [
        f"verify_fail {delta.get('verify_fail_rate_delta', 0):+.4f}",
        f"patch_wrong {delta.get('patch_wrong_rate_delta', 0):+.4f}",
        f"no_test {delta.get('no_test_rate_delta', 0):+.4f}",
        f"tool_wrong {delta.get('tool_wrong_rate_delta', 0):+.4f}",
    ]
    return "prod_delta=" + ", ".join(parts)


def promote_latest_production_failure() -> dict[str, Any]:
    """Enqueue the latest non-B9 production failure for B9 task implementation."""
    from butler.dev_engine.b9_prod_shaped_tasks import B9_PROD_SHAPED_TASK_IDS
    from butler.ops.b9_prod_promoted_registry import (
        binding_for_task,
        resolve_production_failure_to_task,
    )
    from butler.ops.delegate_failure_b9_import import failure_to_b9_candidate
    from butler.ops.delegate_failure_b9_promote import (
        _queue_path,
        enqueue_b9_candidate,
        mark_promotion_implemented,
        promotion_queue_summary,
    )

    rows = load_production_failure_rows(limit=200)
    if not rows:
        return {
            "promoted": False,
            "reason": "no_production_failures",
            "queue_path": str(_queue_path()),
        }

    latest: dict[str, Any] | None = None
    for rec in reversed(rows):
        hit = resolve_production_failure_to_task(rec)
        if hit and hit in B9_PROD_SHAPED_TASK_IDS:
            binding = binding_for_task(hit)
            mark_promotion_implemented(
                hit,
                note=f"auto: matched production audit source={binding.source_task_id if binding else ''}",
            )
            return {
                "promoted": False,
                "reason": "already_implemented",
                "resolved_task_id": hit,
                "source_task_id": binding.source_task_id if binding else "",
                "queue_path": str(_queue_path()),
            }
        if latest is None:
            latest = rec

    if latest is None:
        return {
            "promoted": False,
            "reason": "no_production_failures",
            "queue_path": str(_queue_path()),
        }

    cand = failure_to_b9_candidate(latest)
    suggested = cand.get("suggested_task_id", "")

    queue_path = _queue_path()
    if queue_path.is_file():
        for line in queue_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing = (rec.get("candidate") or {}).get("suggested_task_id", "")
            trace = (rec.get("candidate") or {}).get("trace_id", "")
            if existing == suggested and trace == cand.get("trace_id"):
                return {
                    "promoted": False,
                    "reason": "already_queued",
                    "candidate": cand,
                    "queue_path": str(queue_path),
                }

    queued = enqueue_b9_candidate(cand, source="weekly_production_failure")
    summary = promotion_queue_summary()
    return {
        "promoted": True,
        "queue_path": queued.get("queue_path"),
        "candidate": cand,
        "queue_pending": summary.get("pending", 0),
    }


def run_prod_shaped_live_probe(
    *,
    mode: str | None = None,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """LIVE/oracle probe on B9L_prod_* shaped tasks (production failure templates)."""
    import os
    from pathlib import Path as _Path

    from butler.dev_engine.b9_prod_shaped_tasks import B9_PROD_SHAPED_TASKS
    from butler.dev_engine.llm_delegate_benchmark import B9Mode, resolve_b9_mode, run_b9_task
    from butler.ops.b9_lessons import record_b9_run_lesson
    from butler.ops.b9_prod_promoted_registry import promoted_probe_task_ids

    mode_str = mode or resolve_b9_mode().value
    b9_mode = B9Mode.LIVE if mode_str == "live" else B9Mode.ORACLE
    want = set(task_ids) if task_ids is not None else {t.task_id for t in B9_PROD_SHAPED_TASKS}
    specs = [t for t in B9_PROD_SHAPED_TASKS if t.task_id in want]
    results: list[dict[str, Any]] = []
    passed = 0
    for spec in specs:
        ws = _Path(tempfile.mkdtemp(prefix=f"prod_shaped_{spec.task_id}_"))
        prev = os.environ.get("BUTLER_TOOL_SAFE_ROOT", "")
        os.environ["BUTLER_TOOL_SAFE_ROOT"] = str(ws)
        try:
            result = run_b9_task(spec, ws, mode=b9_mode)
            try:
                record_b9_run_lesson(result, spec)
            except Exception:
                pass
            if result.passed:
                passed += 1
            results.append(
                {
                    "task_id": result.task_id,
                    "passed": result.passed,
                    "tools_used": list(result.tools_used),
                    "failure_reasons": list(result.failure_reasons),
                }
            )
        finally:
            if prev:
                os.environ["BUTLER_TOOL_SAFE_ROOT"] = prev
            else:
                os.environ.pop("BUTLER_TOOL_SAFE_ROOT", None)

    total = len(results)
    return {
        "mode": mode_str,
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "task_ids": [r["task_id"] for r in results],
        "promoted_probe_ids": promoted_probe_task_ids() if task_ids is None else list(task_ids),
        "results": results,
    }


def run_promoted_prod_live_probe(*, mode: str | None = None) -> dict[str, Any]:
    """Probe only audit-promoted B9L_prod_* tasks (phase C inner loop)."""
    from butler.ops.b9_prod_promoted_registry import promoted_probe_task_ids

    return run_prod_shaped_live_probe(mode=mode, task_ids=promoted_probe_task_ids())


__all__ = [
    "compare_production_delegate_delta",
    "format_production_delegate_delta",
    "format_production_delegate_report",
    "is_production_delegate_row",
    "load_production_failure_rows",
    "promote_latest_production_failure",
    "production_snapshots_path",
    "record_production_delegate_snapshot",
    "run_prod_shaped_live_probe",
    "run_promoted_prod_live_probe",
    "summarize_production_delegate_quality",
]
