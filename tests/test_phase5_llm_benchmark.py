"""Phase 5 — O9 B9 LLM delegate benchmark (oracle mode)."""

from __future__ import annotations

from pathlib import Path

from butler.dev_engine.llm_delegate_benchmark import (
    B9Mode,
    B9_TASKS,
    _bind_b9_live_project,
    run_b9_task,
    run_llm_delegate_benchmarks,
)
from butler.orchestrator import ButlerOrchestrator


class TestB9LiveProjectBind:
    def test_bind_b9_live_project_resolves_workspace(self, tmp_path):
        ws = tmp_path / "task_ws"
        ws.mkdir()
        orch = ButlerOrchestrator(user_id="b9-test", channel="cli")
        _bind_b9_live_project(ws, orch, session_key="b9:benchmark")
        pm = orch.project_manager
        proj = pm.get_current(session_key="b9:benchmark")
        assert proj is not None
        assert proj.workspace.resolve() == ws.resolve()
        assert pm.current_project == "__b9_live_benchmark__"
        child_sk = "b9:benchmark:delegate:task-1"
        assert pm.get_current(session_key=child_sk) is not None


class TestB9OracleBenchmark:
    def test_run_b9_oracle_all_pass(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
        report = run_llm_delegate_benchmarks(workspace=tmp_path, mode=B9Mode.ORACLE)
        assert report.total == len(B9_TASKS)
        assert report.passed == report.total
        assert report.pass_rate == 1.0

    def test_verify_detects_unfixed_workspace(self, tmp_path):
        spec = B9_TASKS[0]
        ws = tmp_path / "bad"
        ws.mkdir()
        spec.setup(ws)
        ok, _msg = spec.verify(ws)
        assert ok is False

    def test_llm_benchmark_to_scores(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
        from butler.ops.eval_bridge import llm_benchmark_to_scores

        report = run_llm_delegate_benchmarks(workspace=tmp_path, mode=B9Mode.ORACLE)
        scores = llm_benchmark_to_scores(report)
        assert any(s.name == "llm_benchmark.pass_rate" for s in scores)
        assert scores[0].value == 1.0
