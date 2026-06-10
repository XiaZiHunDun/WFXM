"""Tests for butler.ops.memory_eval — memory benchmark → LangFuse evaluation."""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from butler.ops.memory_eval import (
    benchmark_report_to_dataset_items,
    benchmark_report_to_scores,
    memory_session_to_scores,
    push_memory_benchmark_dataset,
    push_memory_scores,
    MB_DESCRIPTIONS,
)


def _make_benchmark_result(bid="MB1", category="exact_recall", passed=True, score=1.0):
    return SimpleNamespace(
        benchmark_id=bid,
        category=SimpleNamespace(value=category),
        passed=passed,
        score=score,
        error="",
        elapsed_ms=42.0,
        details={"test": True},
        expected=SimpleNamespace(
            min_recall=0.0,
            min_precision=0.0,
            min_survival_rate=1.0,
            max_decay_error=1.0,
            must_filter=False,
        ),
    )


def _make_benchmark_report(n=7, all_pass=True):
    results = []
    categories = [
        ("MB1", "exact_recall"), ("MB2", "semantic_recall"),
        ("MB3", "persistence"), ("MB4", "decay"),
        ("MB5", "capacity"), ("MB6", "fact_compaction"),
        ("MB7", "injection_safety"),
    ]
    for i in range(min(n, len(categories))):
        bid, cat = categories[i]
        results.append(_make_benchmark_result(
            bid=bid, category=cat,
            passed=all_pass, score=1.0 if all_pass else 0.5,
        ))

    passed = sum(1 for r in results if r.passed)
    return SimpleNamespace(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )


def _make_session_metrics():
    return SimpleNamespace(
        writes=20, writes_successful=18,
        prefetch_turns=30, prefetch_hits=25,
        decay_evaluations=50, decay_false_kills=3,
    )


# ── benchmark_report_to_dataset_items ──

def test_benchmark_report_to_dataset_items():
    report = _make_benchmark_report()
    items = benchmark_report_to_dataset_items(report)
    assert len(items) == 7

    for item in items:
        assert item.input["benchmark_id"].startswith("MB")
        assert item.input["description"] != ""
        assert item.source_id.startswith("MB")

    mb1 = items[0]
    assert mb1.input["benchmark_id"] == "MB1"
    assert mb1.expected_output["min_survival_rate"] == 1.0
    assert mb1.metadata["passed"] is True


def test_benchmark_report_to_dataset_items_empty():
    report = SimpleNamespace(results=[])
    items = benchmark_report_to_dataset_items(report)
    assert items == []


# ── benchmark_report_to_scores ──

def test_benchmark_report_to_scores():
    report = _make_benchmark_report()
    scores = benchmark_report_to_scores(report)
    assert len(scores) == 8  # 1 pass_rate + 7 individual
    assert scores[0].name == "memory_benchmark.pass_rate"
    assert scores[0].value == 1.0


def test_benchmark_report_to_scores_with_trace():
    report = _make_benchmark_report()
    scores = benchmark_report_to_scores(report, trace_id="t-123")
    for s in scores:
        assert s.trace_id == "t-123"


# ── memory_session_to_scores ──

def test_memory_session_to_scores():
    metrics = _make_session_metrics()
    scores = memory_session_to_scores(metrics)
    assert len(scores) == 3
    names = {s.name for s in scores}
    assert "memory.write_survival_rate" in names
    assert "memory.first_turn_hit_rate" in names
    assert "memory.decay_error_rate" in names


def test_memory_session_to_scores_with_trace():
    metrics = _make_session_metrics()
    scores = memory_session_to_scores(metrics, trace_id="t-456")
    for s in scores:
        assert s.trace_id == "t-456"


# ── push_memory_benchmark_dataset ──

def test_push_memory_benchmark_dataset():
    report = _make_benchmark_report()
    mock_client = MagicMock()
    mock_client.create_dataset.return_value = SimpleNamespace(id="ds-1")
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        summary = push_memory_benchmark_dataset(report)
        assert summary["dataset_created"] is True
        assert summary["dataset_items"] == 7


def test_push_memory_benchmark_dataset_disabled():
    report = _make_benchmark_report()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=None):
        summary = push_memory_benchmark_dataset(report)
        assert summary["dataset_created"] is False
        assert summary["dataset_items"] == 0


# ── push_memory_scores ──

def test_push_memory_scores_benchmark_only():
    report = _make_benchmark_report()
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        summary = push_memory_scores(report)
        assert summary["scores_pushed"] == 8
        assert summary["total_scores"] == 8


def test_push_memory_scores_with_metrics():
    report = _make_benchmark_report()
    metrics = _make_session_metrics()
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        summary = push_memory_scores(report, metrics=metrics)
        assert summary["total_scores"] == 11  # 8 benchmark + 3 metrics


def test_push_memory_scores_disabled():
    report = _make_benchmark_report()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=None):
        summary = push_memory_scores(report)
        assert summary["scores_pushed"] == 0
        assert summary["scores_failed"] == 8


# ── MB_DESCRIPTIONS ──

def test_all_mb_descriptions_present():
    for i in range(1, 8):
        key = f"MB{i}"
        assert key in MB_DESCRIPTIONS, f"Missing description for {key}"
        assert len(MB_DESCRIPTIONS[key]) > 10
