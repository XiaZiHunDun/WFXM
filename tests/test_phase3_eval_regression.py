"""Phase 3 — benchmark regression gate and dataset sync helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.ops.eval_regression import run_regression_gate


def _fake_dev_report():
    report = MagicMock()
    report.passed = 8
    report.total = 8
    report.pass_rate = 1.0
    report.results = []
    return report


def _fake_mem_report():
    report = MagicMock()
    report.passed = 7
    report.total = 7
    report.results = []
    return report


class TestRegressionGate:
    def test_run_regression_gate_passes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_EVAL_DEV_PASS_RATE_MIN", "0.85")
        monkeypatch.setenv("BUTLER_EVAL_MEM_PASS_RATE_MIN", "0.7")
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "0")
        from butler.config import reload_butler_settings

        reload_butler_settings()

        with patch("butler.dev_engine.dev_benchmark.run_benchmarks", return_value=_fake_dev_report()), \
             patch("butler.memory.memory_benchmark.run_benchmarks", return_value=_fake_mem_report()), \
             patch("butler.ops.eval_diagnostics.b9_in_regression_enabled", return_value=False):
            report = run_regression_gate(push_langfuse=False, sync_dataset=False)

        assert report.passed is True
        assert report.dev_total == 8
        assert report.mem_total == 7
        audit = tmp_path / "audit" / "eval_regression.jsonl"
        assert audit.is_file()

    def test_run_regression_gate_fails_low_rate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_EVAL_DEV_PASS_RATE_MIN", "0.99")

        bad_dev = _fake_dev_report()
        bad_dev.passed = 6
        bad_dev.total = 8
        bad_dev.pass_rate = 0.75
        bad_dev.results = [MagicMock(task_id="B8", passed=False, failure_reasons=["fail"])]

        with patch("butler.dev_engine.dev_benchmark.run_benchmarks", return_value=bad_dev), \
             patch("butler.memory.memory_benchmark.run_benchmarks", return_value=_fake_mem_report()), \
             patch("butler.ops.eval_diagnostics.b9_in_regression_enabled", return_value=False):
            report = run_regression_gate(push_langfuse=False)

        assert report.passed is False
        assert any("dev pass rate" in f for f in report.failures)

    def test_regression_gate_runs_b9_oracle(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_EVAL_B9_IN_REGRESSION", "1")
        from butler.config import reload_butler_settings

        reload_butler_settings()
        b9_report = MagicMock()
        b9_report.passed = 2
        b9_report.total = 2
        b9_report.pass_rate = 1.0
        b9_report.mode = "oracle"
        b9_report.results = []

        with patch("butler.dev_engine.dev_benchmark.run_benchmarks", return_value=_fake_dev_report()), \
             patch("butler.memory.memory_benchmark.run_benchmarks", return_value=_fake_mem_report()), \
             patch(
                 "butler.dev_engine.llm_delegate_benchmark.run_llm_delegate_benchmarks",
                 return_value=b9_report,
             ):
            report = run_regression_gate(push_langfuse=False)

        assert report.b9_total == 2
        assert report.passed is True
        assert (tmp_path / "audit" / "b9_benchmark.jsonl").is_file()

    def test_sync_dataset_uses_unified_sync(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "0")

        sync_summary = {
            "any_pushed": True,
            "total_items": 42,
            "datasets": {},
            "errors": [],
        }

        with patch("butler.dev_engine.dev_benchmark.run_benchmarks", return_value=_fake_dev_report()), \
             patch("butler.memory.memory_benchmark.run_benchmarks", return_value=_fake_mem_report()), \
             patch("butler.ops.eval_diagnostics.b9_in_regression_enabled", return_value=False), \
             patch("butler.ops.dev_eval.sync_all_eval_datasets", return_value=sync_summary) as sync:
            report = run_regression_gate(push_langfuse=False, sync_dataset=True)

        sync.assert_called_once()
        assert report.dataset_synced is True
