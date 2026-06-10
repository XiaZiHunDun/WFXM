"""Tests for butler.ops.eval_scoring — multi-dimensional scoring functions."""

from __future__ import annotations

import pytest

from butler.ops.eval_scoring import (
    ScoreResult,
    MultiDimScore,
    score_intent,
    score_tool_selection,
    score_response_quality,
    score_memory_effectiveness,
    score_turn,
)


# ── ScoreResult ──

def test_score_result_normalized():
    s = ScoreResult(dimension="test", score=0.8, max_score=1.0)
    assert s.normalized == 0.8

    s2 = ScoreResult(dimension="test", score=1.5, max_score=1.0)
    assert s2.normalized == 1.0  # capped

    s3 = ScoreResult(dimension="test", score=-0.5, max_score=1.0)
    assert s3.normalized == 0.0  # floored

    s4 = ScoreResult(dimension="test", score=0.5, max_score=0.0)
    assert s4.normalized == 0.0  # zero max


# ── MultiDimScore ──

def test_multi_dim_score_overall():
    mds = MultiDimScore(scores=[
        ScoreResult(dimension="a", score=1.0),
        ScoreResult(dimension="b", score=0.5),
    ])
    assert abs(mds.overall - 0.75) < 0.01


def test_multi_dim_score_empty():
    mds = MultiDimScore()
    assert mds.overall == 0.0


def test_multi_dim_score_by_dimension():
    mds = MultiDimScore(scores=[
        ScoreResult(dimension="intent", score=0.9),
        ScoreResult(dimension="tools", score=0.7),
    ])
    dims = mds.by_dimension()
    assert dims["intent"] == 0.9
    assert dims["tools"] == 0.7


def test_multi_dim_score_to_eval_scores():
    mds = MultiDimScore(scores=[
        ScoreResult(dimension="intent", score=0.9, comment="good"),
    ])
    eval_scores = mds.to_eval_scores(trace_id="t-1")
    assert len(eval_scores) == 2  # 1 dimension + 1 overall
    assert eval_scores[0].name == "eval.intent"
    assert eval_scores[0].trace_id == "t-1"
    assert eval_scores[1].name == "eval.overall"


# ── score_intent ──

def test_score_intent_exact_match():
    r = score_intent(expected_intent="greeting", actual_intent="greeting")
    assert r.score == 1.0
    assert r.dimension == "intent_accuracy"


def test_score_intent_case_insensitive():
    r = score_intent(expected_intent="Greeting", actual_intent="greeting")
    assert r.score == 1.0


def test_score_intent_partial_match():
    r = score_intent(expected_intent="project", actual_intent="project_status")
    assert r.score == 0.8


def test_score_intent_keyword_match():
    r = score_intent(
        expected_intent="deploy",
        response_text="正在部署到 Docker 容器",
        intent_keywords=["部署", "Docker"],
    )
    assert r.score == 1.0


def test_score_intent_keyword_partial():
    r = score_intent(
        expected_intent="deploy",
        response_text="正在部署",
        intent_keywords=["部署", "Docker", "容器"],
    )
    assert abs(r.score - 1 / 3) < 0.01


def test_score_intent_no_match():
    r = score_intent(expected_intent="deploy", actual_intent="greeting")
    assert r.score == 0.0


# ── score_tool_selection ──

def test_score_tool_selection_perfect():
    r = score_tool_selection(
        expected_tools=["read_file", "write_file"],
        actual_tools=["read_file", "write_file"],
    )
    assert r.score == 1.0


def test_score_tool_selection_partial_recall():
    r = score_tool_selection(
        expected_tools=["read_file", "write_file"],
        actual_tools=["read_file"],
    )
    assert abs(r.score - 0.5) < 0.01


def test_score_tool_selection_with_extra():
    r = score_tool_selection(
        expected_tools=["read_file"],
        actual_tools=["read_file", "list_directory"],
    )
    assert r.score == 0.9  # 1.0 recall - 0.1 penalty


def test_score_tool_selection_no_tools():
    r = score_tool_selection(expected_tools=[], actual_tools=[])
    assert r.score == 1.0


def test_score_tool_selection_unexpected_only():
    r = score_tool_selection(
        expected_tools=[],
        actual_tools=["read_file", "write_file"],
    )
    assert abs(r.score - 0.8) < 0.01  # 1.0 - 2*0.1


def test_score_tool_selection_case_insensitive():
    r = score_tool_selection(
        expected_tools=["Read_File"],
        actual_tools=["read_file"],
    )
    assert r.score == 1.0


# ── score_response_quality ──

def test_score_response_quality_contains_all():
    r = score_response_quality(
        response_text="创建了新项目，切换成功",
        expected_contains=["创建", "切换"],
    )
    assert r.score == 1.0


def test_score_response_quality_contains_partial():
    r = score_response_quality(
        response_text="创建了新项目",
        expected_contains=["创建", "切换"],
    )
    assert abs(r.score - 0.75) < 0.01  # 0.5 contains + 1.0 coherence / 2


def test_score_response_quality_contains_any():
    r = score_response_quality(
        response_text="你好，有什么可以帮助的",
        expected_contains_any=["你好", "您好"],
    )
    assert r.score == 1.0


def test_score_response_quality_max_lines():
    r = score_response_quality(
        response_text="line1\nline2\nline3",
        max_lines=3,
    )
    assert r.score == 1.0


def test_score_response_quality_exceeds_lines():
    r = score_response_quality(
        response_text="l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10",
        max_lines=3,
    )
    assert r.score < 1.0


def test_score_response_quality_empty():
    r = score_response_quality(response_text="")
    assert r.score == 0.0


def test_score_response_quality_no_llm():
    r = score_response_quality(response_text="", no_llm_expected=True)
    assert r.score == 1.0


# ── score_memory_effectiveness ──

def test_score_memory_effectiveness_perfect():
    r = score_memory_effectiveness(
        write_survival_rate=1.0,
        first_turn_hit_rate=1.0,
        decay_error_rate=0.0,
    )
    assert r.score == 1.0


def test_score_memory_effectiveness_mixed():
    r = score_memory_effectiveness(
        write_survival_rate=0.8,
        first_turn_hit_rate=0.6,
        decay_error_rate=0.1,
        weights=(0.4, 0.4, 0.2),
    )
    expected = (0.8 * 0.4 + 0.6 * 0.4 + 0.9 * 0.2) / 1.0
    assert abs(r.score - expected) < 0.01


def test_score_memory_effectiveness_high_decay():
    r = score_memory_effectiveness(
        write_survival_rate=0.9,
        first_turn_hit_rate=0.9,
        decay_error_rate=0.5,
    )
    assert r.score < 0.9


# ── score_turn (combined) ──

def test_score_turn_basic():
    result = score_turn(
        expected_intent="greeting",
        actual_intent="greeting",
        response_text="你好！有什么可以帮助你的？",
        expected_tools=[],
        actual_tools=[],
        expected_contains=["你好"],
    )
    assert len(result.scores) == 3  # intent + tools + quality
    assert result.overall > 0.8


def test_score_turn_with_memory():
    result = score_turn(
        expected_intent="recall",
        actual_intent="recall",
        response_text="已记录",
        include_memory=True,
        memory_s_w=0.9,
        memory_h_1=0.8,
        memory_e_d=0.05,
    )
    assert len(result.scores) == 4
    dims = result.by_dimension()
    assert "memory_effectiveness" in dims


def test_score_turn_no_memory_by_default():
    result = score_turn(
        expected_intent="test",
        actual_intent="test",
        response_text="ok",
    )
    assert len(result.scores) == 3
    dims = result.by_dimension()
    assert "memory_effectiveness" not in dims
