"""Tests for butler.ops.swebench_live_eval."""

from __future__ import annotations

from unittest.mock import patch

from butler.dev_engine.swebench_lite import get_all_instances
from butler.ops.swebench_live_eval import (
    resolve_swe_live_mode,
    run_swebench_live_benchmark,
    select_weekly_instances,
    swe_live_count,
)


def test_select_weekly_instances_count():
    instances = select_weekly_instances(count=3)
    assert len(instances) == 3
    all_ids = {i.instance_id for i in get_all_instances()}
    assert all(i.instance_id in all_ids for i in instances)


def test_swe_live_count_default(monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_SWE_LIVE_COUNT", raising=False)
    assert swe_live_count() == 3


def test_resolve_swe_live_mode_oracle(monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
    assert resolve_swe_live_mode() == "oracle"


def test_resolve_swe_live_mode_live(monkeypatch):
    monkeypatch.setenv("BUTLER_EVAL_LLM_BENCHMARK", "1")
    assert resolve_swe_live_mode() == "live"


def test_run_swebench_live_oracle_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
    inst = select_weekly_instances(count=1)[0]
    report = run_swebench_live_benchmark(
        workspace=tmp_path,
        instances=[inst],
        mode="oracle",
    )
    assert report.total == 1
    assert report.passed == 1
    assert report.pass_rate == 1.0


@patch("butler.ops.eval_bridge.push_scores")
def test_push_swebench_live_scores(mock_push, tmp_path, monkeypatch):
    monkeypatch.delenv("BUTLER_EVAL_LLM_BENCHMARK", raising=False)
    from butler.ops.eval_bridge import EvalReport
    from butler.ops.swebench_live_eval import push_swebench_live_scores

    mock_push.return_value = EvalReport(scores_pushed=2)
    report = run_swebench_live_benchmark(
        instances=select_weekly_instances(count=1),
        mode="oracle",
    )
    summary = push_swebench_live_scores(report)
    assert summary["pass_rate"] == 1.0
    mock_push.assert_called_once()
