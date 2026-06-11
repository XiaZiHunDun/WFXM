"""B1–B10 / MB1–MB7 regression gate for deploy and CI (O7)."""

from __future__ import annotations

from butler.env_parse import float_env
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RegressionReport:
    dev_passed: int = 0
    dev_total: int = 0
    mem_passed: int = 0
    mem_total: int = 0
    dev_pass_rate: float = 0.0
    mem_pass_rate: float = 0.0
    b9_passed: int = 0
    b9_total: int = 0
    b9_pass_rate: float = 0.0
    b9_mode: str = "oracle"
    scores_pushed: int = 0
    dataset_synced: bool = False
    failures: list[str] = field(default_factory=list)
    passed: bool = False
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "dev": f"{self.dev_passed}/{self.dev_total}",
            "mem": f"{self.mem_passed}/{self.mem_total}",
            "dev_pass_rate": round(self.dev_pass_rate, 4),
            "mem_pass_rate": round(self.mem_pass_rate, 4),
            "b9_passed": self.b9_passed,
            "b9_total": self.b9_total,
            "b9_pass_rate": round(self.b9_pass_rate, 4),
            "b9_mode": self.b9_mode,
            "scores_pushed": self.scores_pushed,
            "dataset_synced": self.dataset_synced,
            "failures": self.failures,
            "timestamp": self.timestamp,
            "ts": self.timestamp,
        }


def _min_dev_pass_rate() -> float:
    try:
        return float_env("BUTLER_EVAL_DEV_PASS_RATE_MIN", 0.85)
    except ValueError:
        return 0.85


def _min_mem_pass_rate() -> float:
    try:
        return float_env("BUTLER_EVAL_MEM_PASS_RATE_MIN", 0.7)
    except ValueError:
        return 0.7


def _min_b9_pass_rate() -> float:
    try:
        return float_env("BUTLER_EVAL_B9_PASS_RATE_MIN", 1.0)
    except ValueError:
        return 1.0


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "eval_regression.jsonl"


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_regression_gate(
    *,
    push_langfuse: bool | None = None,
    sync_dataset: bool = False,
) -> RegressionReport:
    """Run DevEngine + Memory benchmarks and optionally push to LangFuse."""
    report = RegressionReport()

    from butler.dev_engine.dev_benchmark import run_benchmarks as run_dev
    from butler.memory.memory_benchmark import run_benchmarks as run_mem

    dev = run_dev()
    report.dev_passed = dev.passed
    report.dev_total = dev.total
    report.dev_pass_rate = dev.pass_rate
    for r in dev.results:
        if not r.passed:
            report.failures.append(f"dev:{r.task_id}: {'; '.join(r.failure_reasons[:2])}")

    mem = run_mem()
    report.mem_passed = mem.passed
    report.mem_total = mem.total
    report.mem_pass_rate = mem.passed / max(1, mem.total)
    for r in mem.results:
        if not r.passed:
            err = r.error or "failed"
            report.failures.append(f"mem:{r.benchmark_id}: {err}")

    from butler.ops.eval_diagnostics import append_b9_audit, b9_in_regression_enabled

    b9 = None
    if b9_in_regression_enabled():
        try:
            from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_llm_delegate_benchmarks

            b9 = run_llm_delegate_benchmarks(mode=B9Mode.ORACLE)
            report.b9_passed = b9.passed
            report.b9_total = b9.total
            report.b9_pass_rate = b9.pass_rate
            report.b9_mode = b9.mode
            append_b9_audit(b9)
            for r in b9.results:
                if not r.passed:
                    report.failures.append(
                        f"b9:{r.task_id}: {'; '.join(r.failure_reasons[:2])}"
                    )
        except Exception as exc:
            logger.warning("B9 benchmark in regression gate failed: %s", exc)
            report.failures.append(f"b9_run: {exc}")

    dev_ok = report.dev_pass_rate >= _min_dev_pass_rate()
    mem_ok = report.mem_pass_rate >= _min_mem_pass_rate()
    b9_ok = (
        report.b9_total == 0
        or report.b9_pass_rate >= _min_b9_pass_rate()
    )
    report.passed = dev_ok and mem_ok and b9_ok
    if not dev_ok:
        report.failures.append(
            f"dev pass rate {report.dev_pass_rate:.0%} < {_min_dev_pass_rate():.0%}"
        )
    if not mem_ok:
        report.failures.append(
            f"mem pass rate {report.mem_pass_rate:.0%} < {_min_mem_pass_rate():.0%}"
        )
    if not b9_ok and report.b9_total:
        report.failures.append(
            f"b9 pass rate {report.b9_pass_rate:.0%} < {_min_b9_pass_rate():.0%}"
        )

    if push_langfuse is None:
        push_langfuse = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in ("1", "true", "yes")

    if push_langfuse:
        try:
            from butler.ops.eval_bridge import (
                dev_benchmark_to_scores,
                llm_benchmark_to_scores,
                memory_benchmark_to_scores,
                push_scores,
            )

            scores = dev_benchmark_to_scores(dev) + memory_benchmark_to_scores(mem)
            if b9 is not None:
                scores.extend(llm_benchmark_to_scores(b9))
            push_report = push_scores(scores)
            report.scores_pushed = push_report.scores_pushed
        except Exception as exc:
            logger.warning("LangFuse benchmark push failed: %s", exc)
            report.failures.append(f"langfuse_push: {exc}")

    if sync_dataset:
        try:
            from butler.ops.dev_eval import sync_all_eval_datasets

            ds_summary = sync_all_eval_datasets(dev_report=dev, mem_report=mem)
            report.dataset_synced = bool(ds_summary.get("any_pushed"))
            if ds_summary.get("errors"):
                for err in ds_summary["errors"]:
                    report.failures.append(f"dataset_sync: {err}")
        except Exception as exc:
            logger.warning("Eval dataset sync failed: %s", exc)
            report.failures.append(f"dataset_sync: {exc}")

    _append_audit(report.summary())
    return report


__all__ = ["RegressionReport", "run_regression_gate"]
