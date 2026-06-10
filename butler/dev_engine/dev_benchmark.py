"""DevEngine comparative benchmarks — standardized tasks to quantify capability.

Layer 3 of the effectiveness measurement system.

Each benchmark task defines:
  - workspace setup (files to create)
  - a sequence of "oracle edits" simulating what an ideal LLM would produce
  - expected outcome (DONE or STUCK)
  - expected metrics thresholds

Benchmark categories:
  B1: Syntax fix          — direct fix, 1 edit, first-pass
  B2: Logic bug fix       — locate + edit + verify loop
  B3: Add function        — create new code
  B4: Refactor rename     — multi-file patch
  B5: Fix failing test    — edit to match test expectation
  B6: Impossible fix      — should terminate as STUCK
  B7: Multi-edit rollback — edit, fail, rollback, re-edit
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from butler.dev_engine.dev_loop import create_dev_state, transition
from butler.dev_engine.dev_metrics import (
    AggregateMetrics,
    DevTaskMetrics,
    MetricsCollector,
    TaskOutcome,
    get_collector,
    reset_collector,
)
from butler.dev_engine.dev_state import (
    DevPhase,
    Diagnostic,
    DiagSeverity,
    EditRecord,
    VerifyResult,
    VerifyStatus,
)
from butler.dev_engine.edit_ops import apply_patch, apply_write


class BenchmarkCategory(str, Enum):
    SYNTAX_FIX = "syntax_fix"
    LOGIC_BUG = "logic_bug"
    ADD_FUNCTION = "add_function"
    REFACTOR = "refactor"
    FIX_TEST = "fix_test"
    IMPOSSIBLE = "impossible"
    ROLLBACK = "rollback"


@dataclass
class BenchmarkExpected:
    """Expected outcome and thresholds for a benchmark task."""

    outcome: TaskOutcome
    max_iterations: int = 20
    max_edits: int = 5
    expect_first_pass: bool = False
    expect_fix_loop: bool = False


@dataclass
class BenchmarkResult:
    """Result of running a single benchmark task."""

    task_id: str
    category: BenchmarkCategory
    description: str
    passed: bool
    metrics: DevTaskMetrics | None = None
    expected: BenchmarkExpected | None = None
    failure_reasons: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "category": self.category.value,
            "description": self.description,
            "passed": self.passed,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "failure_reasons": self.failure_reasons,
        }
        if self.metrics:
            d["metrics"] = self.metrics.to_dict()
        return d


@dataclass
class BenchmarkReport:
    """Aggregate report across all benchmark tasks."""

    results: list[BenchmarkResult] = field(default_factory=list)
    aggregate: AggregateMetrics | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        lines = [
            f"基准测试报告: {self.passed}/{self.total} 通过 ({self.pass_rate:.0%})",
            "",
        ]
        by_cat: dict[str, list[BenchmarkResult]] = {}
        for r in self.results:
            by_cat.setdefault(r.category.value, []).append(r)

        for cat, rs in by_cat.items():
            cat_pass = sum(1 for r in rs if r.passed)
            lines.append(f"  {cat}: {cat_pass}/{len(rs)}")
            for r in rs:
                mark = "✓" if r.passed else "✗"
                lines.append(f"    {mark} {r.description}")
                for reason in r.failure_reasons:
                    lines.append(f"      → {reason}")

        if self.aggregate:
            agg = self.aggregate
            lines.extend([
                "",
                "聚合指标:",
                f"  完成率: {agg.completion_rate:.1%}",
                f"  首次通过率: {agg.first_pass_rate:.1%}",
                f"  编辑精度: {agg.avg_edit_precision:.1%}",
                f"  修复收敛率: {agg.avg_fix_convergence:.1%}",
                f"  平均迭代(DONE): {agg.avg_iterations_to_done:.1f}",
            ])
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 3),
            "results": [r.to_dict() for r in self.results],
            "aggregate": self.aggregate.to_dict() if self.aggregate else None,
        }


# ── Benchmark Task Definitions ──────────────────────────────────


def _check_result(
    metrics: DevTaskMetrics,
    expected: BenchmarkExpected,
) -> list[str]:
    """Validate metrics against expected thresholds. Returns failure reasons."""
    failures: list[str] = []
    if metrics.outcome != expected.outcome:
        failures.append(
            f"outcome: got {metrics.outcome.value}, expected {expected.outcome.value}"
        )
    if metrics.total_iterations > expected.max_iterations:
        failures.append(
            f"iterations: {metrics.total_iterations} > max {expected.max_iterations}"
        )
    if metrics.total_edits > expected.max_edits:
        failures.append(
            f"edits: {metrics.total_edits} > max {expected.max_edits}"
        )
    if expected.expect_first_pass and not metrics.first_pass:
        failures.append("expected first-pass but entered fix loop")
    if expected.expect_fix_loop and not metrics.entered_fix_loop:
        failures.append("expected fix loop but never entered FIX")
    return failures


def _run_b1_syntax_fix(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B1: Fix a syntax error — simple direct fix, first-pass expected."""
    task_id = "b1_syntax_fix"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=6,
        max_edits=1,
        expect_first_pass=True,
    )

    state = create_dev_state("fix syntax error in hello.py", task_id=task_id)

    f = tmp_path / "hello.py"
    f.write_text("def greet(name)\n    return f'Hello {name}'\n")

    state = transition(state, "plan_trivial")
    record, err = apply_patch(f, "def greet(name)\n", "def greet(name):\n")
    assert err == "", err
    state.record_edit(record)
    state = transition(state, "edit_success", edit_record=record)
    state = transition(state, "verify_pass")

    m = collector.get_task_metrics(task_id)
    if m is None:
        m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.SYNTAX_FIX,
        description="修复 Python 语法错误（缺少冒号）",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b2_logic_bug(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B2: Fix a logic bug — requires locate + edit + verify_fail + fix + verify_pass."""
    task_id = "b2_logic_bug"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=10,
        max_edits=2,
        expect_fix_loop=True,
    )

    state = create_dev_state("fix off-by-one in range_sum", task_id=task_id)

    f = tmp_path / "math_utils.py"
    f.write_text("def range_sum(n):\n    return sum(range(n))\n")

    state = transition(state, "plan_complete")
    state = transition(state, "files_found")

    record1, _ = apply_patch(f, "range(n)", "range(n + 1)")
    state.record_edit(record1)
    state = transition(state, "edit_success", edit_record=record1)

    vr_fail = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[Diagnostic(
            file="math_utils.py", line=2,
            severity=DiagSeverity.ERROR,
            message="test_range_sum: assert range_sum(3) == 6, got 6 (test wrong)",
        )],
    )
    state = transition(state, "verify_fail", verify_result=vr_fail)
    state = transition(state, "fix_applied")

    state = transition(state, "verify_pass")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.LOGIC_BUG,
        description="修复 off-by-one 逻辑错误",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b3_add_function(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B3: Add a new function — create + edit + verify."""
    task_id = "b3_add_function"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=6,
        max_edits=1,
        expect_first_pass=True,
    )

    state = create_dev_state("add fibonacci function", task_id=task_id)

    f = tmp_path / "fib.py"
    state = transition(state, "plan_trivial")

    record, _ = apply_write(f, "def fibonacci(n: int) -> int:\n"
                               "    if n <= 1:\n"
                               "        return n\n"
                               "    return fibonacci(n - 1) + fibonacci(n - 2)\n")
    state.record_edit(record)
    state = transition(state, "edit_success", edit_record=record)
    state = transition(state, "verify_pass")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.ADD_FUNCTION,
        description="新增 fibonacci 函数",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b4_refactor(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B4: Rename refactor — multi-file patch."""
    task_id = "b4_refactor"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=8,
        max_edits=2,
        expect_first_pass=True,
    )

    state = create_dev_state("rename get_data to fetch_data", task_id=task_id)

    f1 = tmp_path / "api.py"
    f1.write_text("def get_data(url):\n    return requests.get(url)\n")
    f2 = tmp_path / "main.py"
    f2.write_text("from api import get_data\nresult = get_data('/api')\n")

    state = transition(state, "plan_complete")
    state = transition(state, "files_found")

    r1, _ = apply_patch(f1, "def get_data(", "def fetch_data(")
    state.record_edit(r1)
    state = transition(state, "edit_success", edit_record=r1)

    state = transition(state, "verify_pass")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.REFACTOR,
        description="跨文件重命名 get_data → fetch_data",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b5_fix_test(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B5: Fix code to pass a failing test."""
    task_id = "b5_fix_test"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=10,
        max_edits=2,
        expect_fix_loop=True,
    )

    state = create_dev_state("fix add() to handle negative numbers", task_id=task_id)

    f = tmp_path / "calc.py"
    f.write_text("def add(a, b):\n    if a < 0 or b < 0:\n        return 0\n    return a + b\n")

    state = transition(state, "plan_trivial")

    r1, _ = apply_patch(f, "    if a < 0 or b < 0:\n        return 0\n", "")
    state.record_edit(r1)
    state = transition(state, "edit_success", edit_record=r1)

    vr_fail = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[Diagnostic(
            file="calc.py", line=2, severity=DiagSeverity.ERROR,
            message="IndentationError: expected indented block",
        )],
    )
    state = transition(state, "verify_fail", verify_result=vr_fail)
    state = transition(state, "fix_applied")

    state = transition(state, "verify_pass")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.FIX_TEST,
        description="修复 add() 使测试通过",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b6_impossible(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B6: Impossible fix — should exhaust K_max and enter STUCK."""
    task_id = "b6_impossible"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.STUCK,
        max_iterations=20,
        max_edits=5,
        expect_fix_loop=True,
    )

    state = create_dev_state(
        "fix unsolvable type error", task_id=task_id,
        max_fix_rounds=2, max_iterations=50,
    )

    f = tmp_path / "broken.py"
    f.write_text("x: int = 'not an int'\n")

    state = transition(state, "plan_trivial")
    r1, _ = apply_write(f, "x: int = 42  # attempt 1\n")
    state.record_edit(r1)
    state = transition(state, "edit_success", edit_record=r1)

    for _ in range(4):
        if state.is_terminal:
            break
        vr = VerifyResult(
            status=VerifyStatus.FAIL,
            diagnostics=[Diagnostic(
                file="broken.py", line=1, severity=DiagSeverity.ERROR,
                message="persistent type error",
            )],
        )
        state = transition(state, "verify_fail", verify_result=vr)
        if state.is_terminal:
            break
        state = transition(state, "fix_applied")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.IMPOSSIBLE,
        description="不可修复的类型错误（应进入 STUCK）",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _run_b7_rollback(tmp_path: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B7: Edit-fail-rollback-reedit cycle."""
    task_id = "b7_rollback"
    expected = BenchmarkExpected(
        outcome=TaskOutcome.DONE,
        max_iterations=12,
        max_edits=2,
        expect_fix_loop=True,
    )

    state = create_dev_state("fix with rollback needed", task_id=task_id)

    f = tmp_path / "service.py"
    f.write_text("def process(data):\n    return data.upper()\n")

    state = transition(state, "plan_trivial")

    r1, _ = apply_patch(f, "data.upper()", "data.lower()")
    state.record_edit(r1)
    state = transition(state, "edit_success", edit_record=r1)

    vr_fail = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[Diagnostic(
            file="service.py", line=2, severity=DiagSeverity.ERROR,
            message="test_process: expected UPPER, got lower",
        )],
    )
    state = transition(state, "verify_fail", verify_result=vr_fail)

    from butler.dev_engine.edit_ops import undo_edit
    undo_edit(r1)
    state = transition(state, "fix_rollback")

    state = transition(state, "plan_trivial")
    r2, _ = apply_patch(f, "data.upper()", "data.strip().upper()")
    state.record_edit(r2)
    state = transition(state, "edit_success", edit_record=r2)
    state = transition(state, "verify_pass")

    m = _find_completed(collector, task_id)
    failures = _check_result(m, expected) if m else ["metrics not found"]

    return BenchmarkResult(
        task_id=task_id,
        category=BenchmarkCategory.ROLLBACK,
        description="编辑失败后回滚并重新编辑",
        passed=len(failures) == 0,
        metrics=m,
        expected=expected,
        failure_reasons=failures,
    )


def _find_completed(collector: MetricsCollector, task_id: str) -> DevTaskMetrics | None:
    """Find metrics in completed or active tasks."""
    m = collector.get_task_metrics(task_id)
    if m:
        return m
    for cm in collector._completed:
        if cm.task_id == task_id:
            return cm
    return None


# ── Benchmark Runner ────────────────────────────────────────────


def _run_b8_swebench(workspace: Path, collector: MetricsCollector) -> BenchmarkResult:
    """B8: SWE-bench Lite adapted — oracle-apply + verify on 15 instances."""
    from butler.dev_engine.swebench_lite import _instances

    instances = _instances()
    pass_count = 0
    fail_reasons: list[str] = []

    for inst in instances:
        inst_dir = workspace / inst.instance_id
        inst_dir.mkdir(parents=True, exist_ok=True)
        try:
            inst.setup_workspace(inst_dir)
            inst.apply_oracle(inst_dir)
            if inst.verify(inst_dir):
                pass_count += 1
            else:
                fail_reasons.append(f"{inst.instance_id}: verify failed after oracle patch")
        except Exception as exc:
            fail_reasons.append(f"{inst.instance_id}: {exc}")

    all_passed = pass_count == len(instances)
    return BenchmarkResult(
        task_id="B8_swebench_lite",
        category=BenchmarkCategory.LOGIC_BUG,
        description=f"SWE-bench Lite: {pass_count}/{len(instances)} oracle-verify passed",
        passed=all_passed,
        failure_reasons=fail_reasons,
        expected=BenchmarkExpected(
            outcome=TaskOutcome.DONE,
            max_iterations=1,
            max_edits=len(instances),
        ),
    )


_BUILTIN_BENCHMARKS: list[Callable[[Path, MetricsCollector], BenchmarkResult]] = [
    _run_b1_syntax_fix,
    _run_b2_logic_bug,
    _run_b3_add_function,
    _run_b4_refactor,
    _run_b5_fix_test,
    _run_b6_impossible,
    _run_b7_rollback,
    _run_b8_swebench,
]


def run_benchmarks(
    workspace: Path | None = None,
    benchmarks: list[Callable] | None = None,
) -> BenchmarkReport:
    """Run all benchmark tasks and produce a report.

    Uses an isolated MetricsCollector so benchmarks don't pollute
    production metrics.
    """
    import tempfile

    bench_list = benchmarks or _BUILTIN_BENCHMARKS
    collector = MetricsCollector()

    # Temporarily swap the global collector
    from butler.dev_engine import dev_metrics
    old_collector = dev_metrics._global_collector
    dev_metrics._global_collector = collector

    try:
        report = BenchmarkReport()
        for bench_fn in bench_list:
            if workspace:
                tmp = workspace / bench_fn.__name__
                tmp.mkdir(parents=True, exist_ok=True)
            else:
                tmp = Path(tempfile.mkdtemp(prefix="butler_bench_"))

            t0 = time.time()
            try:
                result = bench_fn(tmp, collector)
                result.elapsed_seconds = time.time() - t0
            except Exception as exc:
                result = BenchmarkResult(
                    task_id=bench_fn.__name__,
                    category=BenchmarkCategory.SYNTAX_FIX,
                    description=f"CRASH: {bench_fn.__name__}",
                    passed=False,
                    failure_reasons=[f"Exception: {exc}"],
                    elapsed_seconds=time.time() - t0,
                )
            report.results.append(result)

        report.aggregate = collector.aggregate()
        return report
    finally:
        dev_metrics._global_collector = old_collector
