"""Production dev delegate outcomes vs coding experience hits (P0 effectiveness metrics)."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_OUTCOMES_NAME = "delegate_dev_outcomes.jsonl"


def outcomes_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _OUTCOMES_NAME


def should_record_dev_delegate_outcome(
    *,
    role: str,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    task_preview: str = "",
    task_id: str = "",
    project: str = "",
) -> bool:
    """True for production-shaped dev delegates (excludes B9/SWE/drill noise)."""
    from butler.ops.b9_prod_weekly import is_production_audit_noise

    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return False
    cat = str(category or (category_meta or {}).get("category") or "").strip().lower()
    if cat in ("b9-benchmark", "swe-benchmark", "lingwen-drill", "lingwen-prod-sample"):
        return False
    preview = str(task_preview or "").lower()
    if "[category:b9-benchmark]" in preview or "[category:swe-benchmark]" in preview:
        return False
    if "[category:lingwen-drill]" in preview or "[category:lingwen-prod-sample]" in preview:
        return False
    tid = str(task_id or "")
    if tid.startswith("B9L_") or tid.startswith("SWE-"):
        return False
    if project:
        rec = {
            "role": "dev",
            "project": project,
            "capture_source": "delegate_pipeline",
            "task_preview": preview,
            "task_id": tid,
        }
        if is_production_audit_noise(rec):
            return False
        return True
    if "test_b9.py" in preview and "lingwen" not in preview and "demo/hello" not in preview:
        return False
    return True


def record_dev_delegate_outcome(
    *,
    session_key: str = "",
    role: str = "dev",
    project: str = "",
    task_id: str = "",
    task_preview: str = "",
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    success: bool = False,
    verify_passed: bool | None = None,
    experience_id: str = "",
    experience_mode: str = "",
    reactivation_count: int = 0,
    capture_source: str = "delegate_pipeline",
) -> dict[str, Any]:
    """Append one dev delegate outcome row for effectiveness analytics."""
    if not should_record_dev_delegate_outcome(
        role=role,
        category=category,
        category_meta=category_meta,
        task_preview=task_preview,
        task_id=task_id,
        project=project,
    ):
        return {"recorded": False, "reason": "filtered"}

    exp_id = str(experience_id or "").strip()
    row: dict[str, Any] = {
        "ts": time.time(),
        "session_key": session_key,
        "role": role,
        "project": project,
        "task_id": task_id,
        "task_preview": (task_preview or "")[:300],
        "success": bool(success),
        "verify_passed": verify_passed,
        "experience_hit": bool(exp_id),
        "experience_id": exp_id,
        "experience_mode": experience_mode,
        "reactivation_count": int(reactivation_count or 0),
        "capture_source": capture_source,
    }
    if verify_passed is False:
        from butler.ops.production_failure_experience import classify_production_failure

        row["classification"] = classify_production_failure(
            failure_reason="verify_fail",
            dev_engine={"verify_passed": False},
        )
    path = outcomes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"recorded": True, "experience_hit": row["experience_hit"]}


def load_dev_delegate_outcomes(*, limit: int = 500) -> list[dict[str, Any]]:
    path = outcomes_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def summarize_prod_experience_effectiveness(
    *,
    limit: int = 500,
    window_days: float = 7.0,
) -> dict[str, Any]:
    """Layered prod metrics: verify pass rate by experience_hit + repeat failures."""
    rows = load_dev_delegate_outcomes(limit=limit)
    hit_pass = 0
    hit_total = 0
    miss_pass = 0
    miss_total = 0
    reactivation_rows = 0
    for row in rows:
        vp = row.get("verify_passed")
        if vp is None:
            continue
        if row.get("experience_hit"):
            hit_total += 1
            if vp is True:
                hit_pass += 1
        else:
            miss_total += 1
            if vp is True:
                miss_pass += 1
        if int(row.get("reactivation_count") or 0) > 0:
            reactivation_rows += 1

    repeat = summarize_prod_repeat_failures(window_days=window_days, clean=True)
    return {
        "outcomes_total": len(rows),
        "scored_total": hit_total + miss_total,
        "experience_hit_total": hit_total,
        "experience_miss_total": miss_total,
        "prod_verify_pass_rate_hit": round(hit_pass / hit_total, 4) if hit_total else None,
        "prod_verify_pass_rate_miss": round(miss_pass / miss_total, 4) if miss_total else None,
        "prod_verify_pass_delta_hit_minus_miss": (
            round((hit_pass / hit_total) - (miss_pass / miss_total), 4)
            if hit_total and miss_total
            else None
        ),
        "reactivation_outcome_rows": reactivation_rows,
        "prod_repeat_fail_7d": repeat,
        "path": str(outcomes_path()),
    }


def summarize_prod_repeat_failures(
    *,
    window_days: float = 7.0,
    clean: bool = True,
    limit: int = 500,
) -> dict[str, Any]:
    """Count project+classification buckets with 2+ failures inside the window."""
    from butler.ops.b9_prod_weekly import load_production_failure_rows
    from butler.ops.production_failure_experience import classify_production_failure

    cutoff = time.time() - window_days * 86400
    rows = load_production_failure_rows(limit=limit, clean=clean)
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for rec in rows:
        ts = float(rec.get("ts") or 0)
        if ts and ts < cutoff:
            continue
        project = str(rec.get("project") or "").strip() or "_no_project"
        classification = classify_production_failure(
            failure_reason=str(rec.get("failure_reason") or ""),
            issues=rec.get("issues") if isinstance(rec.get("issues"), list) else None,
            dev_engine={"verify_passed": rec.get("verify_passed")},
        )
        buckets[(project, classification)].append(ts or time.time())

    repeat_pairs: list[dict[str, Any]] = []
    for (project, classification), times in sorted(buckets.items()):
        if len(times) >= 2:
            repeat_pairs.append(
                {
                    "project": project,
                    "classification": classification,
                    "count": len(times),
                }
            )
    return {
        "window_days": window_days,
        "repeat_bucket_count": len(repeat_pairs),
        "repeat_pairs": repeat_pairs[:12],
        "clean": clean,
    }


def format_prod_experience_effectiveness(summary: dict[str, Any] | None = None) -> str:
    data = summary if summary is not None else summarize_prod_experience_effectiveness()
    repeat = data.get("prod_repeat_fail_7d") or {}
    lines = [
        "=== Prod experience effectiveness ===",
        f"outcomes_total={data.get('outcomes_total', 0)} scored={data.get('scored_total', 0)}",
        (
            "prod_verify_pass_rate_hit="
            f"{data.get('prod_verify_pass_rate_hit')} "
            f"(n={data.get('experience_hit_total', 0)})"
        ),
        (
            "prod_verify_pass_rate_miss="
            f"{data.get('prod_verify_pass_rate_miss')} "
            f"(n={data.get('experience_miss_total', 0)})"
        ),
        f"hit_minus_miss={data.get('prod_verify_pass_delta_hit_minus_miss')}",
        f"reactivation_outcome_rows={data.get('reactivation_outcome_rows', 0)}",
        (
            f"prod_repeat_fail_7d buckets={repeat.get('repeat_bucket_count', 0)} "
            f"pairs={repeat.get('repeat_pairs', [])}"
        ),
    ]
    return "\n".join(lines)


__all__ = [
    "format_prod_experience_effectiveness",
    "load_dev_delegate_outcomes",
    "outcomes_path",
    "record_dev_delegate_outcome",
    "should_record_dev_delegate_outcome",
    "summarize_prod_experience_effectiveness",
    "summarize_prod_repeat_failures",
]
