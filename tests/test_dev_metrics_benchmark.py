"""Tests for DevEngine effectiveness metrics (Layer 2) and benchmarks (Layer 3).

Validates:
  - MetricsCollector lifecycle and aggregation
  - Per-task metrics accuracy
  - Transition event emission from dev_loop
  - Benchmark runner and all 8 built-in benchmarks (B1–B8)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest


class TestMetricsCollectorLifecycle:
    """Layer 2: MetricsCollector unit tests."""

    def test_start_and_end_task(self):
        from butler.dev_engine.dev_metrics import MetricsCollector, TaskOutcome

        c = MetricsCollector()
        c.on_task_start("t1", "test task")
        assert c.get_task_metrics("t1") is not None

        c.on_transition("t1", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("t1", "EDIT", "edit_success", "VERIFY")
        c.on_transition("t1", "VERIFY", "verify_pass", "DONE")

        assert c.get_task_metrics("t1") is None
        assert len(c._completed) == 1
        assert c._completed[0].outcome == TaskOutcome.DONE

    def test_stuck_task(self):
        from butler.dev_engine.dev_metrics import MetricsCollector, TaskOutcome

        c = MetricsCollector()
        c.on_task_start("t2", "stuck task")
        c.on_transition("t2", "PLAN", "plan_complete", "LOCATE")
        c.on_transition("t2", "LOCATE", "locate_timeout", "STUCK")

        assert c._completed[0].outcome == TaskOutcome.STUCK

    def test_abandoned_task(self):
        from butler.dev_engine.dev_metrics import MetricsCollector, TaskOutcome

        c = MetricsCollector()
        c.on_task_start("t3", "abandoned")
        c.on_task_abandon("t3")
        assert c._completed[0].outcome == TaskOutcome.ABANDONED

    def test_edit_precision_tracking(self):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c = MetricsCollector()
        c.on_task_start("t4", "precision test")
        c.on_transition("t4", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("t4", "EDIT", "edit_success", "VERIFY")
        c.on_transition("t4", "VERIFY", "verify_pass", "DONE")

        m = c._completed[0]
        assert m.total_edits == 1
        assert m.verify_passes == 1
        assert m.edit_precision == 1.0

    def test_fix_loop_tracking(self):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c = MetricsCollector()
        c.on_task_start("t5", "fix loop")
        c.on_transition("t5", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("t5", "EDIT", "edit_success", "VERIFY")
        c.on_transition("t5", "VERIFY", "verify_fail", "FIX")
        c.on_transition("t5", "FIX", "fix_applied", "VERIFY")
        c.on_transition("t5", "VERIFY", "verify_pass", "DONE")

        m = c._completed[0]
        assert m.entered_fix_loop is True
        assert m.fix_entries == 1
        assert m.fix_exits_to_verify == 1
        assert m.first_pass is False

    def test_rollback_tracking(self):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c = MetricsCollector()
        c.on_task_start("t6", "rollback")
        c.on_transition("t6", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("t6", "EDIT", "edit_success", "VERIFY")
        c.on_transition("t6", "VERIFY", "verify_fail", "FIX")
        c.on_transition("t6", "FIX", "fix_rollback", "PLAN")
        c.on_transition("t6", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("t6", "EDIT", "edit_success", "VERIFY")
        c.on_transition("t6", "VERIFY", "verify_pass", "DONE")

        m = c._completed[0]
        assert m.total_rollbacks == 1
        assert m.fix_exits_to_plan == 1


class TestAggregateMetrics:
    """Layer 2: Aggregate metrics computation."""

    def _build_collector(self):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c = MetricsCollector()
        # Task 1: DONE, first-pass
        c.on_task_start("a1", "easy")
        c.on_transition("a1", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("a1", "EDIT", "edit_success", "VERIFY")
        c.on_transition("a1", "VERIFY", "verify_pass", "DONE")

        # Task 2: DONE, with fix loop
        c.on_task_start("a2", "medium")
        c.on_transition("a2", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("a2", "EDIT", "edit_success", "VERIFY")
        c.on_transition("a2", "VERIFY", "verify_fail", "FIX")
        c.on_transition("a2", "FIX", "fix_applied", "VERIFY")
        c.on_transition("a2", "VERIFY", "verify_pass", "DONE")

        # Task 3: STUCK
        c.on_task_start("a3", "hard")
        c.on_transition("a3", "PLAN", "plan_complete", "LOCATE")
        c.on_transition("a3", "LOCATE", "locate_timeout", "STUCK")

        return c

    def test_completion_rate(self):
        c = self._build_collector()
        agg = c.aggregate()
        assert agg.total_tasks == 3
        assert agg.completed_tasks == 2
        assert agg.stuck_tasks == 1
        assert abs(agg.completion_rate - 2 / 3) < 0.01

    def test_first_pass_rate(self):
        c = self._build_collector()
        agg = c.aggregate()
        assert abs(agg.first_pass_rate - 0.5) < 0.01

    def test_stuck_rate(self):
        c = self._build_collector()
        agg = c.aggregate()
        assert abs(agg.stuck_rate - 1 / 3) < 0.01

    def test_avg_iterations(self):
        c = self._build_collector()
        agg = c.aggregate()
        assert agg.avg_iterations_to_done > 0

    def test_to_dict_has_all_fields(self):
        c = self._build_collector()
        d = c.aggregate().to_dict()
        expected_keys = {
            "total_tasks", "completed_tasks", "stuck_tasks", "abandoned_tasks",
            "in_progress_tasks", "completion_rate", "stuck_rate", "first_pass_rate",
            "avg_edit_precision", "avg_fix_convergence",
            "avg_iterations_to_done", "avg_edits_to_done",
        }
        assert expected_keys.issubset(d.keys())


class TestMetricsPersistence:
    """Layer 2: Metrics save/load."""

    def test_save_and_load(self, tmp_path):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c1 = MetricsCollector()
        c1.on_task_start("p1", "persist test")
        c1.on_transition("p1", "PLAN", "plan_trivial", "EDIT")
        c1.on_transition("p1", "EDIT", "edit_success", "VERIFY")
        c1.on_transition("p1", "VERIFY", "verify_pass", "DONE")

        f = tmp_path / "metrics.json"
        c1.save_to_file(f)
        assert f.exists()

        c2 = MetricsCollector()
        c2.load_from_file(f)
        assert len(c2._completed) == 1
        agg = c2.aggregate()
        assert agg.completed_tasks == 1

    def test_export_json_valid(self):
        from butler.dev_engine.dev_metrics import MetricsCollector

        c = MetricsCollector()
        c.on_task_start("j1", "json test")
        c.on_transition("j1", "PLAN", "plan_trivial", "EDIT")
        c.on_transition("j1", "EDIT", "edit_success", "VERIFY")
        c.on_transition("j1", "VERIFY", "verify_pass", "DONE")

        data = json.loads(c.export_json())
        assert "aggregate" in data
        assert "completed_tasks" in data


class TestDevLoopMetricsEmission:
    """Layer 2: dev_loop.transition emits metrics to global collector."""

    def test_transition_emits_to_collector(self):
        from butler.dev_engine import dev_metrics
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_metrics import MetricsCollector

        old = dev_metrics._global_collector
        collector = MetricsCollector()
        dev_metrics._global_collector = collector

        try:
            state = create_dev_state("emit test", task_id="emit_1")
            state = transition(state, "plan_trivial")
            state = transition(state, "edit_success")
            state = transition(state, "verify_pass")

            assert len(collector._completed) == 1
            m = collector._completed[0]
            assert m.task_id == "emit_1"
            assert m.outcome.value == "DONE"
            assert m.total_edits == 1
            assert m.verify_passes == 1
        finally:
            dev_metrics._global_collector = old


class TestDevMetricsTool:
    """Layer 2: dev_metrics tool handler."""

    def test_tool_returns_aggregate(self):
        from butler.dev_engine import dev_metrics
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_metrics import MetricsCollector
        from butler.dev_engine.dev_tools import tool_dev_metrics

        old = dev_metrics._global_collector
        collector = MetricsCollector()
        dev_metrics._global_collector = collector

        try:
            state = create_dev_state("tool test", task_id="tool_1")
            state = transition(state, "plan_trivial")
            state = transition(state, "edit_success")
            state = transition(state, "verify_pass")

            result = tool_dev_metrics(detail="summary")
            assert "aggregate" in result
            assert result["aggregate"]["completed_tasks"] == 1
        finally:
            dev_metrics._global_collector = old

    def test_tool_full_detail(self):
        from butler.dev_engine import dev_metrics
        from butler.dev_engine.dev_loop import create_dev_state, transition
        from butler.dev_engine.dev_metrics import MetricsCollector
        from butler.dev_engine.dev_tools import tool_dev_metrics

        old = dev_metrics._global_collector
        collector = MetricsCollector()
        dev_metrics._global_collector = collector

        try:
            state = create_dev_state("detail test", task_id="detail_1")
            state = transition(state, "plan_trivial")
            state = transition(state, "edit_success")
            state = transition(state, "verify_pass")

            result = tool_dev_metrics(detail="full")
            assert "completed_tasks" in result
            assert len(result["completed_tasks"]) == 1
        finally:
            dev_metrics._global_collector = old


# ===================================================================
# Layer 3: Benchmark Tests
# ===================================================================


class TestBenchmarkRunner:
    """Layer 3: Run all 8 built-in benchmarks."""

    def test_run_all_benchmarks(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        assert report.total == 8, f"Expected 8 benchmarks, got {report.total}"

        for r in report.results:
            if not r.passed:
                print(f"FAIL: {r.task_id} — {r.failure_reasons}")

        assert report.passed == 8, (
            f"{report.failed} benchmarks failed:\n"
            + "\n".join(
                f"  {r.task_id}: {r.failure_reasons}"
                for r in report.results if not r.passed
            )
        )

    def test_benchmark_report_summary(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        summary = report.summary()
        assert "基准测试报告" in summary
        assert "8/8" in summary

    def test_benchmark_report_aggregate(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        assert report.aggregate is not None
        assert report.aggregate.total_tasks == 7
        assert report.aggregate.completion_rate > 0.5
        assert report.aggregate.stuck_rate > 0


class TestIndividualBenchmarks:
    """Layer 3: Validate individual benchmark semantics."""

    def test_b1_syntax_fix_is_first_pass(self, tmp_path):
        from butler.dev_engine.dev_benchmark import _run_b1_syntax_fix
        from butler.dev_engine.dev_metrics import MetricsCollector

        from butler.dev_engine import dev_metrics
        old = dev_metrics._global_collector
        c = MetricsCollector()
        dev_metrics._global_collector = c

        try:
            r = _run_b1_syntax_fix(tmp_path, c)
            assert r.passed
            assert r.metrics is not None
            assert r.metrics.first_pass is True
        finally:
            dev_metrics._global_collector = old

    def test_b6_impossible_enters_stuck(self, tmp_path):
        from butler.dev_engine.dev_benchmark import _run_b6_impossible
        from butler.dev_engine.dev_metrics import MetricsCollector, TaskOutcome

        from butler.dev_engine import dev_metrics
        old = dev_metrics._global_collector
        c = MetricsCollector()
        dev_metrics._global_collector = c

        try:
            r = _run_b6_impossible(tmp_path, c)
            assert r.passed
            assert r.metrics is not None
            assert r.metrics.outcome == TaskOutcome.STUCK
        finally:
            dev_metrics._global_collector = old

    def test_b7_rollback_recovers(self, tmp_path):
        from butler.dev_engine.dev_benchmark import _run_b7_rollback
        from butler.dev_engine.dev_metrics import MetricsCollector, TaskOutcome

        from butler.dev_engine import dev_metrics
        old = dev_metrics._global_collector
        c = MetricsCollector()
        dev_metrics._global_collector = c

        try:
            r = _run_b7_rollback(tmp_path, c)
            assert r.passed
            assert r.metrics is not None
            assert r.metrics.outcome == TaskOutcome.DONE
            assert r.metrics.total_rollbacks >= 1
        finally:
            dev_metrics._global_collector = old


class TestBenchmarkMetricsIntegrity:
    """Layer 3: Verify metrics make sense across benchmark suite."""

    def test_completion_rate_matches_expected(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        agg = report.aggregate
        assert agg is not None
        # 6 DONE + 1 STUCK = 6/7 completion rate
        assert abs(agg.completion_rate - 6 / 7) < 0.02

    def test_stuck_rate_matches_expected(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        agg = report.aggregate
        assert agg is not None
        assert abs(agg.stuck_rate - 1 / 7) < 0.02

    def test_first_pass_rate_positive(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        agg = report.aggregate
        assert agg is not None
        assert agg.first_pass_rate > 0

    def test_edit_precision_bounded(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        agg = report.aggregate
        assert agg is not None
        assert 0.0 <= agg.avg_edit_precision <= 1.0

    def test_fix_convergence_bounded(self, tmp_path):
        from butler.dev_engine.dev_benchmark import run_benchmarks

        report = run_benchmarks(workspace=tmp_path)
        agg = report.aggregate
        assert agg is not None
        assert 0.0 <= agg.avg_fix_convergence <= 1.0
