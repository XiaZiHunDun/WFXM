"""Tests for butler.ops.eval_experiment — variant comparison."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.ops.eval_experiment import (
    EXPERIMENT_VARIANTS,
    run_eval_experiment,
    run_variant_benchmark,
    variant_to_scores,
)


def test_variant_to_scores():
    from butler.ops.eval_experiment import VariantResult

    vr = VariantResult(variant="baseline", b9_passed=8, b9_total=8, b9_pass_rate=1.0)
    scores = variant_to_scores("dev-delegate", vr)
    assert scores[0].name == "eval_experiment.dev-delegate.baseline.b9_pass_rate"
    assert scores[0].value == 1.0


@patch("butler.ops.eval_bridge.push_scores")
@patch("butler.dev_engine.llm_delegate_benchmark.run_llm_delegate_benchmarks")
def test_run_eval_experiment_two_variants(mock_b9, mock_push, tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "0")
    from butler.config import reload_butler_settings

    reload_butler_settings()

    report_mock = MagicMock()
    report_mock.passed = 8
    report_mock.total = 8
    report_mock.pass_rate = 1.0
    report_mock.mode = "oracle"
    mock_b9.return_value = report_mock
    mock_push.return_value = MagicMock(scores_pushed=0)

    report = run_eval_experiment(
        experiment_id="test-exp",
        variants={"baseline": {}, "strict_ck": EXPERIMENT_VARIANTS["strict_ck"]},
        push_langfuse=False,
    )
    assert len(report.variants) == 2
    assert report.variants[0].b9_pass_rate == 1.0
    audit = tmp_path / "audit" / "eval_experiments.jsonl"
    assert audit.is_file()


@patch("butler.dev_engine.llm_delegate_benchmark.run_llm_delegate_benchmarks")
def test_run_variant_benchmark_applies_patch(mock_b9, tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()

    report_mock = MagicMock()
    report_mock.passed = 6
    report_mock.total = 8
    report_mock.pass_rate = 0.75
    report_mock.mode = "oracle"
    mock_b9.return_value = report_mock

    vr = run_variant_benchmark("strict_ck", EXPERIMENT_VARIANTS["strict_ck"])
    assert vr.variant == "strict_ck"
    assert vr.b9_pass_rate == 0.75
    from butler.ops.eval_config_overrides import load_overrides

    assert load_overrides() == {}
