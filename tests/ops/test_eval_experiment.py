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


def test_experiment_variants_include_failure_class():
    assert "failure_class" in EXPERIMENT_VARIANTS
    assert "strict_ck_rescue" in EXPERIMENT_VARIANTS
    assert EXPERIMENT_VARIANTS["failure_class"]["coding_guidance_max_cases"] == 8


def test_promote_b9_experiment_winner_strict_ck(tmp_path, monkeypatch):
    from butler.ops.eval_config_overrides import load_overrides, promote_b9_experiment_winner
    from butler.ops.eval_experiment import VariantResult

    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)

    variants = [
        VariantResult(variant="baseline", b9_passed=6, b9_total=22, b9_pass_rate=6 / 22),
        VariantResult(variant="strict_ck", b9_passed=7, b9_total=22, b9_pass_rate=7 / 22),
    ]
    action = promote_b9_experiment_winner(variants)
    assert action is not None
    assert action["winner"] == "strict_ck"
    data = load_overrides()
    assert data.get("coding_guidance_max_cases") == 8
    assert data.get("coding_knowledge_strict_experience") is True
