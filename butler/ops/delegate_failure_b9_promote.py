"""Promote production delegate failures into the B9 promotion queue.

Workflow:
  1. ``export_b9_candidates`` / weekly review surfaces candidates
  2. Annotate in LangFuse (tool_wrong / patch_wrong / no_test / verify_fail)
  3. ``promote_from_audit`` enqueues + emits Python scaffold for ``b9_*_tasks.py``
  4. Human completes setup/verify/oracle → append to ``b9_prod_shaped_tasks`` or LIVE set
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from butler.ops.delegate_failure_b9_import import (
    export_b9_candidates,
    failure_to_b9_candidate,
    load_failure_records,
)

DEMO_AUDIT_RECORD: dict[str, Any] = {
    "role": "dev",
    "task_id": "demo-fix-greet-return",
    "trace_id": "trace-demo-greet-001",
    "failure_reason": "verify_fail",
    "task_preview": (
        "Fix greet.py so greet() returns 'hello' instead of 'hi'. "
        "Only modify greet.py; test_b9.py must pass."
    ),
    "issues": ["pytest failed: assert 'hi' == 'hello'"],
    "verify_passed": False,
}

_QUEUE_NAME = "b9_promotion_queue.jsonl"


def _queue_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _QUEUE_NAME


def _append_queue(record: dict[str, Any]) -> Path:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("queued_at", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def generate_task_scaffold(candidate: dict[str, Any]) -> str:
    """Emit a copy-paste Python skeleton for a new B9TaskSpec."""
    task_id = candidate.get("suggested_task_id") or "B9L_prod_new_case"
    description = candidate.get("description") or "Production delegate failure"
    prompt = candidate.get("delegate_prompt") or "Fix the workspace so tests pass."
    reason = candidate.get("failure_reason") or "unknown"
    slug = task_id.replace("B9L_prod_", "")

    return f'''# Paste into butler/dev_engine/b9_prod_shaped_tasks.py after implementing hooks.
# failure_reason: {reason}

def _setup_{slug}(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    # TODO: reproduce workspace from sanitized production context
    raise NotImplementedError("setup for {task_id}")


def _oracle_{slug}(ws: Path) -> None:
    # TODO: oracle patch that makes verify pass in CI
    raise NotImplementedError("oracle for {task_id}")


def _verify_{slug}(ws: Path) -> tuple[bool, str]:
    # TODO: pytest or structural assertion
    return False, "not implemented"


B9TaskSpec(
    task_id="{task_id}",
    description="{description}",
    delegate_prompt={prompt!r},
    setup=_setup_{slug},
    verify=_verify_{slug},
    oracle_apply=_oracle_{slug},
    tags=("prod_shaped", "{reason}", "pytest"),
),
'''


def enqueue_b9_candidate(
    candidate: dict[str, Any],
    *,
    source: str = "manual",
) -> dict[str, Any]:
    """Append a B9 candidate dict to the promotion queue."""
    queue_rec = {
        "candidate": candidate,
        "status": "pending_implementation",
        "source": source,
    }
    path = _append_queue(queue_rec)
    return {"queued": True, "queue_path": str(path), "candidate": candidate}


def promote_from_audit(
    *,
    index: int = -1,
    annotate_reason: str = "",
) -> dict[str, Any]:
    """Enqueue one audit record and return scaffold for implementation."""
    records = load_failure_records()
    if not records:
        return {
            "promoted": False,
            "reason": "empty_audit",
            "hint": "Run dev delegate with BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1 first",
            "queue_path": str(_queue_path()),
        }

    rec = records[index]
    cand = failure_to_b9_candidate(rec)
    if annotate_reason:
        cand["failure_reason"] = annotate_reason
        cand["description"] = f"Production delegate failure ({annotate_reason})"

    scaffold = generate_task_scaffold(cand)
    queue_rec = {
        "candidate": cand,
        "scaffold_lines": scaffold.count("\n") + 1,
        "status": "pending_implementation",
    }
    path = _append_queue(queue_rec)

    return {
        "promoted": True,
        "queue_path": str(path),
        "candidate": cand,
        "scaffold": scaffold,
        "modeled_templates": {
            "verify_fail": "B9L_prod_verify_fail",
            "patch_wrong": "B9L_prod_patch_wrong",
            "no_test": "B9L_prod_no_test",
        },
    }


def mark_promotion_implemented(
    task_id: str,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Mark a queued B9 candidate as implemented (rewrites matching queue rows)."""
    path = _queue_path()
    if not path.is_file():
        return {"updated": False, "reason": "queue_missing", "task_id": task_id}

    updated = 0
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cand_id = (rec.get("candidate") or {}).get("suggested_task_id", "")
        if cand_id == task_id and rec.get("status") == "pending_implementation":
            rec["status"] = "implemented"
            rec["implemented_at"] = time.time()
            if note:
                rec["implementation_note"] = note
            updated += 1
        rows.append(rec)

    if not updated:
        return {"updated": False, "reason": "not_found_or_already_done", "task_id": task_id}

    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return {"updated": True, "task_id": task_id, "rows_updated": updated, "queue_path": str(path)}


def dismiss_spurious_promotion_queue_items() -> dict[str, Any]:
    """Mark pending queue rows that match SWE/benchmark noise as dismissed."""
    path = _queue_path()
    if not path.is_file():
        return {"dismissed": 0}
    dismissed = 0
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cand = rec.get("candidate") or {}
        preview = str(cand.get("delegate_prompt") or "").lower()
        tid = str(cand.get("suggested_task_id") or "")
        if (
            rec.get("status") == "pending_implementation"
            and ("swe-benchmark" in preview or "[category:swe" in preview)
        ):
            rec["status"] = "dismissed"
            rec["dismissed_at"] = time.time()
            rec["dismiss_reason"] = "swe_benchmark_noise"
            dismissed += 1
        rows.append(rec)
    if dismissed:
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    return {"dismissed": dismissed, "queue_path": str(path)}


def sync_promotion_queue_with_tasks() -> dict[str, Any]:
    """Auto-mark queue items implemented when task_id exists in B9_PROD_SHAPED_TASKS."""
    from butler.dev_engine.b9_prod_shaped_tasks import B9_PROD_SHAPED_TASK_IDS

    results: list[dict[str, Any]] = []
    for task_id in B9_PROD_SHAPED_TASK_IDS:
        out = mark_promotion_implemented(
            task_id,
            note="auto: task present in b9_prod_shaped_tasks",
        )
        if out.get("updated"):
            results.append(out)
    return {"synced": len(results), "items": results}


def promotion_queue_summary(*, limit: int = 50) -> dict[str, Any]:
    path = _queue_path()
    if not path.is_file():
        return {"total": 0, "pending": 0, "recent": [], "queue_path": str(path)}

    recent: list[dict[str, Any]] = []
    pending = 0
    from butler.ops.delegate_failure_b9_promote_ops import read_promotion_queue_records_safe

    for rec in read_promotion_queue_records_safe(path):
        if rec.get("status") == "pending_implementation":
            pending += 1
        recent.append(rec)
    return {
        "total": len(recent),
        "pending": pending,
        "recent": recent[-limit:],
        "queue_path": str(path),
    }


def seed_demo_failure_audit(*, force: bool = False) -> dict[str, Any]:
    """Append one realistic demo row to ``delegate_failures.jsonl``."""
    from butler.ops.delegate_failure_capture import failure_audit_summary

    summary = failure_audit_summary()
    if summary.get("total") and not force:
        return {
            "seeded": False,
            "reason": "audit_not_empty",
            "audit_path": summary.get("audit_path"),
            "total": summary.get("total"),
        }

    record = {**DEMO_AUDIT_RECORD, "ts": time.time(), "demo": True}
    from butler.ops.delegate_failure_capture import _append_audit

    _append_audit(record)
    return {
        "seeded": True,
        "audit_path": failure_audit_summary().get("audit_path"),
        "record": record,
    }


def run_promotion_demo(*, force_seed: bool = False) -> dict[str, Any]:
    """Seed demo audit (if empty) → promote → export bundle. For pipeline smoke."""
    seed = seed_demo_failure_audit(force=force_seed)
    promote = promote_from_audit(index=-1)
    bundle = export_promotion_bundle(audit_limit=10)
    queue = promotion_queue_summary()
    return {
        "seed": seed,
        "promote": {k: v for k, v in promote.items() if k != "scaffold"},
        "scaffold": promote.get("scaffold", ""),
        "bundle": bundle,
        "queue_pending": queue.get("pending", 0),
        "modeled_templates": promote.get("modeled_templates", {}),
    }


def export_promotion_bundle(
    *,
    audit_limit: int = 20,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Write candidates + queue summary for offline review."""
    from butler.config import get_butler_home

    base = out_dir or (get_butler_home() / "audit" / "b9_promotion")
    base.mkdir(parents=True, exist_ok=True)

    candidates_path = base / "candidates.json"
    export_b9_candidates(limit=audit_limit, out_path=candidates_path)

    summary = promotion_queue_summary()
    summary_path = base / "queue_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "candidates_path": str(candidates_path),
        "queue_summary_path": str(summary_path),
        "audit_total": export_b9_candidates(limit=audit_limit).get("total", 0),
        "queue_pending": summary.get("pending", 0),
    }


__all__ = [
    "DEMO_AUDIT_RECORD",
    "dismiss_spurious_promotion_queue_items",
    "enqueue_b9_candidate",
    "export_promotion_bundle",
    "generate_task_scaffold",
    "mark_promotion_implemented",
    "promote_from_audit",
    "promotion_queue_summary",
    "run_promotion_demo",
    "seed_demo_failure_audit",
    "sync_promotion_queue_with_tasks",
]
