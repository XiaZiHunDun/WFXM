"""Tests for butler.ops.eval_bridge — evaluation bridge to LangFuse."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from butler.ops.eval_bridge import (
    EvalScore,
    DatasetItem,
    EvalReport,
    push_score,
    push_scores,
    create_dataset,
    push_dataset_item,
    push_dataset_items,
    dev_benchmark_to_scores,
    memory_benchmark_to_scores,
    memory_metrics_to_scores,
    corpus_run_to_scores,
)


# ── EvalScore dataclass ──

def test_eval_score_defaults():
    s = EvalScore(name="test", value=0.95)
    assert s.name == "test"
    assert s.value == 0.95
    assert s.comment == ""
    assert s.category == ""
    assert s.metadata == {}
    assert s.timestamp > 0


def test_eval_report_summary():
    r = EvalReport(scores_pushed=5, scores_failed=1, errors=["e1"])
    s = r.summary()
    assert s["scores_pushed"] == 5
    assert s["scores_failed"] == 1
    assert "e1" in s["errors"]


# ── push_score ──

def test_push_score_disabled():
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=None):
        result = push_score(EvalScore(name="test", value=1.0))
        assert result is False


def test_push_score_success():
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        result = push_score(EvalScore(
            name="test",
            value=0.9,
            comment="good",
            trace_id="t1",
        ))
        assert result is True
        mock_client.score.assert_called_once()
        call_kwargs = mock_client.score.call_args[1]
        assert call_kwargs["name"] == "test"
        assert call_kwargs["value"] == 0.9
        assert call_kwargs["comment"] == "good"
        assert call_kwargs["trace_id"] == "t1"


def test_push_score_exception():
    mock_client = MagicMock()
    mock_client.score.side_effect = RuntimeError("API error")
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        result = push_score(EvalScore(name="test", value=1.0))
        assert result is False


# ── push_scores batch ──

def test_push_scores_batch():
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        scores = [
            EvalScore(name="s1", value=0.8),
            EvalScore(name="s2", value=0.9),
        ]
        report = push_scores(scores)
        assert report.scores_pushed == 2
        assert report.scores_failed == 0
        mock_client.flush.assert_called_once()


def test_push_scores_partial_failure():
    mock_client = MagicMock()
    call_count = 0

    def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("fail")

    mock_client.score.side_effect = side_effect
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        scores = [
            EvalScore(name="s1", value=0.8),
            EvalScore(name="s2", value=0.9),
            EvalScore(name="s3", value=0.7),
        ]
        report = push_scores(scores)
        assert report.scores_pushed == 2
        assert report.scores_failed == 1


# ── create_dataset ──

def test_create_dataset_disabled():
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=None):
        result = create_dataset("test-ds")
        assert result is None


def test_create_dataset_success():
    mock_client = MagicMock()
    mock_ds = SimpleNamespace(id="ds-123")
    mock_client.create_dataset.return_value = mock_ds
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        result = create_dataset("test-ds", "description")
        assert result == "ds-123"
        mock_client.create_dataset.assert_called_once_with(name="test-ds", description="description")


# ── push_dataset_item ──

def test_push_dataset_item_disabled():
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=None):
        result = push_dataset_item("ds", DatasetItem(input={"q": "hello"}))
        assert result is False


def test_push_dataset_item_success():
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        item = DatasetItem(
            input={"q": "hello"},
            expected_output={"intent": "greeting"},
            metadata={"source": "test"},
        )
        result = push_dataset_item("ds", item)
        assert result is True
        mock_client.create_dataset_item.assert_called_once()


def test_push_dataset_items_batch():
    mock_client = MagicMock()
    with patch("butler.ops.eval_bridge._get_langfuse_client", return_value=mock_client):
        items = [
            DatasetItem(input={"q": "a"}, expected_output={"r": "1"}),
            DatasetItem(input={"q": "b"}, expected_output={"r": "2"}),
        ]
        report = push_dataset_items("ds", items)
        assert report.dataset_items_pushed == 2


# ── dev_benchmark_to_scores ──

def test_dev_benchmark_to_scores():
    result = SimpleNamespace(
        benchmark_id="B1",
        category=SimpleNamespace(value="syntax_fix"),
        passed=True,
        score=1.0,
        error="",
        elapsed_ms=42.0,
        details={"fix": "semicolon"},
    )
    report = SimpleNamespace(total=7, passed=6, failed=1, results=[result])
    scores = dev_benchmark_to_scores(report)
    assert len(scores) == 2
    assert scores[0].name == "dev_benchmark.pass_rate"
    assert abs(scores[0].value - 6 / 7) < 0.01
    assert scores[1].name == "dev_benchmark.B1"
    assert scores[1].value == 1.0


# ── memory_benchmark_to_scores ──

def test_memory_benchmark_to_scores():
    result = SimpleNamespace(
        benchmark_id="MB1",
        category=SimpleNamespace(value="exact_recall"),
        passed=True,
        score=0.95,
        error="",
        elapsed_ms=10.0,
        details={},
    )
    report = SimpleNamespace(total=7, passed=7, failed=0, results=[result])
    scores = memory_benchmark_to_scores(report)
    assert len(scores) == 2
    assert scores[0].name == "memory_benchmark.pass_rate"
    assert scores[0].value == 1.0
    assert scores[1].name == "memory_benchmark.MB1"


# ── memory_metrics_to_scores ──

def test_memory_metrics_to_scores():
    metrics = SimpleNamespace(
        writes=10,
        writes_successful=8,
        prefetch_turns=20,
        prefetch_hits=15,
        decay_evaluations=100,
        decay_false_kills=5,
    )
    scores = memory_metrics_to_scores(metrics)
    assert len(scores) == 3
    names = [s.name for s in scores]
    assert "memory.write_survival_rate" in names
    assert "memory.first_turn_hit_rate" in names
    assert "memory.decay_error_rate" in names

    sw = next(s for s in scores if s.name == "memory.write_survival_rate")
    assert abs(sw.value - 0.8) < 0.01

    h1 = next(s for s in scores if s.name == "memory.first_turn_hit_rate")
    assert abs(h1.value - 0.75) < 0.01

    ed = next(s for s in scores if s.name == "memory.decay_error_rate")
    assert abs(ed.value - 0.05) < 0.01


def test_memory_metrics_to_scores_zero():
    metrics = SimpleNamespace(
        writes=0, writes_successful=0,
        prefetch_turns=0, prefetch_hits=0,
        decay_evaluations=0, decay_false_kills=0,
    )
    scores = memory_metrics_to_scores(metrics)
    assert all(s.value == 0.0 for s in scores)


# ── corpus_run_to_scores ──

def test_corpus_run_to_scores_basic():
    scores = corpus_run_to_scores("wechat", total=100, passed=92)
    assert len(scores) == 1
    assert scores[0].name == "corpus.wechat.pass_rate"
    assert abs(scores[0].value - 0.92) < 0.01


def test_corpus_run_to_scores_full():
    scores = corpus_run_to_scores(
        "agentloop",
        total=183,
        passed=180,
        intent_accuracy=0.95,
        tool_accuracy=0.88,
        avg_latency_ms=1200.0,
    )
    assert len(scores) == 4
    names = [s.name for s in scores]
    assert "corpus.agentloop.pass_rate" in names
    assert "corpus.agentloop.intent_accuracy" in names
    assert "corpus.agentloop.tool_accuracy" in names
    assert "corpus.agentloop.avg_latency_ms" in names
