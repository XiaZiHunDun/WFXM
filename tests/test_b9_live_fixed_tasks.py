"""Tests for B9 LIVE fixed task set and oracle regression."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS, B9_LIVE_FIXED_TASK_IDS
from butler.dev_engine.llm_delegate_benchmark import (
    B9Mode,
    B9_TASKS,
    run_b9_live_fixed_benchmarks,
    run_llm_delegate_benchmarks,
)


class TestB9LiveFixedTasks:
    def test_fixed_set_count(self):
        assert len(B9_LIVE_FIXED_TASKS) == 16
        assert len(B9_LIVE_FIXED_TASK_IDS) == 16

    def test_all_tasks_merged_into_b9_tasks(self):
        for spec in B9_LIVE_FIXED_TASKS:
            assert any(t.task_id == spec.task_id for t in B9_TASKS)

    def test_oracle_all_pass(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
        report = run_b9_live_fixed_benchmarks(workspace=tmp_path, mode=B9Mode.ORACLE)
        assert report.total == 16
        assert report.passed == 16

    def test_full_b9_oracle_includes_live_fixed(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
        report = run_llm_delegate_benchmarks(workspace=tmp_path, mode=B9Mode.ORACLE)
        assert report.total == len(B9_TASKS)
        assert report.passed == report.total

    def test_stuck_task_expect_pass_false(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
        stuck = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_stuck_unsolvable")
        assert stuck.expect_pass is False
