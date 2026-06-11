"""Tests for B9 promotion queue and prod-shaped tasks."""

from __future__ import annotations

import json

from butler.dev_engine.b9_prod_shaped_tasks import B9_PROD_SHAPED_TASKS
from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_b9_task
from butler.ops.delegate_failure_b9_promote import (
    generate_task_scaffold,
    promote_from_audit,
    promotion_queue_summary,
    run_promotion_demo,
    seed_demo_failure_audit,
)


def test_prod_shaped_oracle_pass(tmp_path, monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
    for spec in B9_PROD_SHAPED_TASKS:
        ws = tmp_path / spec.task_id
        ws.mkdir()
        result = run_b9_task(spec, ws, mode=B9Mode.ORACLE)
        assert result.passed, f"{spec.task_id}: {result.failure_reasons}"


def test_generate_task_scaffold_contains_task_id():
    text = generate_task_scaffold({
        "suggested_task_id": "B9L_prod_fix_hello",
        "description": "Production delegate failure (verify_fail)",
        "delegate_prompt": "Fix hello.py",
        "failure_reason": "verify_fail",
    })
    assert "B9L_prod_fix_hello" in text
    assert "verify_fail" in text
    assert "B9TaskSpec" in text


def test_promote_from_audit_empty(monkeypatch):
    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote.load_failure_records",
        lambda **_: [],
    )
    result = promote_from_audit()
    assert result["promoted"] is False
    assert result["reason"] == "empty_audit"


def test_promote_from_audit_enqueues(tmp_path, monkeypatch):
    audit_rec = {
        "task_preview": "Fix calc.py negative handling",
        "failure_reason": "patch_wrong",
        "task_id": "job-99",
    }

    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote.load_failure_records",
        lambda **_: [audit_rec],
    )
    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote._queue_path",
        lambda: tmp_path / "b9_promotion_queue.jsonl",
    )

    result = promote_from_audit(index=0, annotate_reason="patch_wrong")
    assert result["promoted"] is True
    assert "scaffold" in result
    assert (tmp_path / "b9_promotion_queue.jsonl").is_file()
    line = (tmp_path / "b9_promotion_queue.jsonl").read_text(encoding="utf-8").strip()
    queued = json.loads(line)
    assert queued["status"] == "pending_implementation"

    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote._queue_path",
        lambda: tmp_path / "b9_promotion_queue.jsonl",
    )
    summary = promotion_queue_summary()
    assert summary["pending"] == 1


def test_seed_demo_and_promote_e2e(tmp_path, monkeypatch):
    audit = tmp_path / "delegate_failures.jsonl"
    queue = tmp_path / "b9_promotion_queue.jsonl"
    promo_dir = tmp_path / "b9_promotion"

    monkeypatch.setattr(
        "butler.ops.delegate_failure_capture._audit_path",
        lambda: audit,
    )
    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote._queue_path",
        lambda: queue,
    )

    seed = seed_demo_failure_audit()
    assert seed["seeded"] is True
    assert audit.is_file()

    seed2 = seed_demo_failure_audit()
    assert seed2["seeded"] is False
    assert seed2["reason"] == "audit_not_empty"

    result = promote_from_audit(index=-1)
    assert result["promoted"] is True
    assert "B9L_prod_demo_fix_greet_return" in result["scaffold"]
    assert queue.is_file()

    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote._queue_path",
        lambda: queue,
    )
    from butler.ops.delegate_failure_b9_promote import export_promotion_bundle

    bundle = export_promotion_bundle(audit_limit=5, out_dir=promo_dir)
    assert (promo_dir / "candidates.json").is_file()
    assert bundle["audit_total"] == 1


def test_run_promotion_demo_force_seed(tmp_path, monkeypatch):
    audit = tmp_path / "delegate_failures.jsonl"
    queue = tmp_path / "b9_promotion_queue.jsonl"
    promo_dir = tmp_path / "b9_promotion"

    monkeypatch.setattr(
        "butler.ops.delegate_failure_capture._audit_path",
        lambda: audit,
    )
    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote._queue_path",
        lambda: queue,
    )

    def _bundle(**kwargs):
        out_dir = kwargs.get("out_dir") or promo_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        from butler.ops.delegate_failure_b9_import import export_b9_candidates

        export_b9_candidates(limit=5, out_path=out_dir / "candidates.json")
        return {
            "candidates_path": str(out_dir / "candidates.json"),
            "queue_summary_path": str(out_dir / "queue_summary.json"),
            "audit_total": 1,
            "queue_pending": 1,
        }

    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_promote.export_promotion_bundle",
        _bundle,
    )

    demo = run_promotion_demo(force_seed=True)
    assert demo["seed"]["seeded"] is True
    assert demo["promote"]["promoted"] is True
    assert demo["queue_pending"] >= 1
