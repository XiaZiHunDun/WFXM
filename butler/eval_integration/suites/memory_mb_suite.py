"""Memory MB1–MB7 benchmark suite."""

from __future__ import annotations

import os

from butler.contracts.eval_ports import SuiteRunResult
from butler.env_parse import float_env


def _min_mem_pass_rate() -> float:
    try:
        return float_env("BUTLER_EVAL_MEM_PASS_RATE_MIN", 0.7)
    except ValueError:
        return 0.7


class MemoryMbSuite:
    suite_id = "memory_mb"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.memory.memory_benchmark import run_benchmarks

        if push_langfuse is None:
            push_langfuse = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in (
                "1",
                "true",
                "yes",
            )
        report = run_benchmarks()
        pass_rate = report.passed / max(1, report.total)
        threshold = _min_mem_pass_rate()
        ok = pass_rate >= threshold
        if push_langfuse:
            try:
                from butler.ops.memory_eval import push_memory_scores

                push_memory_scores(report)
            except Exception:
                pass
        if warn_only and not ok:
            ok = True
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "pass_rate": round(pass_rate, 4),
                "passed": report.passed,
                "total": report.total,
                "threshold": threshold,
            },
            error="" if ok else f"mem pass rate {pass_rate:.0%} < {threshold:.0%}",
        )
