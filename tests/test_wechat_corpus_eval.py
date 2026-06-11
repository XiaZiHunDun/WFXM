"""Tests for butler.ops.wechat_corpus_eval."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.ops.wechat_corpus_eval import (
    _parse_pytest_output,
    catalog_delegate_stats,
    push_wechat_corpus_scores,
)


def test_parse_pytest_output():
    out = "....................\n120 passed in 4.32s"
    counts = _parse_pytest_output(out)
    assert counts["passed"] == 120
    assert counts["total"] == 120


def test_catalog_delegate_stats():
    stats = catalog_delegate_stats()
    assert stats.get("catalog_total", 0) > 0
    assert "delegate_entries" in stats


@patch("butler.ops.eval_bridge.push_scores")
def test_push_wechat_corpus_scores(mock_push):
    from butler.ops.eval_bridge import EvalReport

    mock_push.return_value = EvalReport(scores_pushed=1)
    summary = push_wechat_corpus_scores({
        "total": 10,
        "passed": 9,
        "pass_rate": 0.9,
        "catalog": {"delegate_ratio": 0.2},
    })
    assert summary["scores_pushed"] == 1
    mock_push.assert_called_once()


@patch("butler.ops.wechat_corpus_eval.subprocess.run")
def test_run_wechat_gateway_corpus_parses_passed(mock_run):
    from butler.ops.wechat_corpus_eval import run_wechat_gateway_corpus

    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="50 passed in 2s\n",
        stderr="",
    )
    summary = run_wechat_gateway_corpus()
    assert summary["passed"] == 50
    assert summary["pass_rate"] == 1.0
