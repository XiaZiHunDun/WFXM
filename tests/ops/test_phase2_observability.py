"""Phase 2 observability — per-turn scoring, synth injection, hard feedback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.dev_engine.coding_knowledge import (
    CodingKnowledgeContext,
    CodingElement,
    format_coding_guidance_block,
    process_task,
    TheoremLibrary,
    ExperienceLibrary,
)
from butler.dev_engine.dev_context import dev_state_context_block
from butler.dev_engine.dev_state import DevState, CodingKnowledgeSummary
from butler.ops.eval_actions import apply_hard_feedback
from butler.ops.eval_config_overrides import (
    adjust_memory_half_life,
    effective_memory_half_life_days,
    load_overrides,
)
from butler.ops.eval_feedback import FeedbackReport, FeedbackSuggestion
from butler.ops.eval_turn import push_turn_scores, score_runtime_turn


class TestRuntimeTurnScoring:
    def test_score_runtime_turn_basic(self):
        multi = score_runtime_turn(
            user_text="帮我切换项目",
            response_text="已切换到灵文1号项目",
            tools_used=["switch_project"],
            session_id="",
            include_memory=False,
        )
        dims = multi.by_dimension()
        assert "intent_accuracy" in dims
        assert "tool_selection" in dims
        assert "response_quality" in dims
        assert multi.overall > 0

    def test_push_turn_scores_disabled(self):
        with patch("butler.ops.eval_turn.push_scores") as mock_push:
            mock_push.return_value = MagicMock(scores_pushed=0, scores_failed=0, errors=[])
            multi, report = push_turn_scores(
                user_text="hello",
                response_text="world",
                trace_id="trace-1",
            )
            assert multi.overall >= 0
            mock_push.assert_called_once()


class TestCodingGuidanceInjection:
    def test_format_coding_guidance_block(self):
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary(theorem_lib=tlib)
        ctx = process_task(["python", "error", "retry"], tlib, xlib)
        block = format_coding_guidance_block(ctx)
        assert "<coding-guidance>" in block
        assert "Theorem constraints" in block
        assert "Equivalence-class" in block

    def test_dev_context_includes_guidance(self):
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary(theorem_lib=tlib)
        ctx = process_task(["python", "patch"], tlib, xlib)
        state = DevState()
        state.coding_knowledge = CodingKnowledgeSummary(
            mode=ctx.mode,
            activated_theorem_ids=sorted(ctx.activated_theorems.keys()),
            activated_elements=[e.value for e in ctx.activated_elements],
        )
        state._coding_knowledge_ctx = ctx
        block = dev_state_context_block(state)
        assert "<coding-guidance>" in block


class TestHardFeedback:
    def _reload_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()

    def test_adjust_memory_half_life(self, tmp_path, monkeypatch):
        self._reload_home(monkeypatch, tmp_path)
        new_val = adjust_memory_half_life(direction="up", base=30.0, step_days=5.0)
        assert new_val == 35.0
        assert load_overrides()["memory_half_life_days"] == 35.0
        assert effective_memory_half_life_days(30.0) == 35.0

    def test_apply_hard_feedback_memory_action(self, tmp_path, monkeypatch):
        self._reload_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK", "1")
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK_HOURS", "0")
        report = FeedbackReport(
            suggestions=[
                FeedbackSuggestion(
                    category="performance",
                    severity="warning",
                    message="memory low",
                    metric_name="memory_effectiveness",
                    metric_value=0.3,
                    threshold=0.5,
                )
            ]
        )
        result = apply_hard_feedback(report)
        assert result.get("applied") is True
        audit = tmp_path / "audit" / "eval_feedback.jsonl"
        assert audit.is_file()
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert record["action"] == "adjust_memory_half_life"

    def test_apply_hard_feedback_dev_action(self, tmp_path, monkeypatch):
        self._reload_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK", "1")
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK_HOURS", "0")
        report = FeedbackReport(
            suggestions=[
                FeedbackSuggestion(
                    category="quality",
                    severity="critical",
                    message="dev low",
                    metric_name="dev_benchmark.pass_rate",
                    metric_value=0.5,
                    threshold=0.7,
                )
            ]
        )
        result = apply_hard_feedback(report)
        assert result.get("applied") is True
        overrides = load_overrides()
        assert overrides.get("coding_knowledge_strict_experience") is True
        assert overrides.get("coding_guidance_max_cases") == 8

    def test_apply_hard_feedback_llm_action(self, tmp_path, monkeypatch):
        self._reload_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK", "1")
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK_HOURS", "0")
        report = FeedbackReport(
            suggestions=[
                FeedbackSuggestion(
                    category="quality",
                    severity="warning",
                    message="b9 low",
                    metric_name="llm_benchmark.pass_rate",
                    metric_value=0.6,
                    threshold=1.0,
                )
            ]
        )
        result = apply_hard_feedback(report)
        assert result.get("applied") is True
        overrides = load_overrides()
        assert overrides.get("dev_max_fix_rounds") == 4
        assert overrides.get("delegate_max_iterations") == 28

    def test_apply_hard_feedback_tool_routing_action(self, tmp_path, monkeypatch):
        self._reload_home(monkeypatch, tmp_path)
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK", "1")
        monkeypatch.setenv("BUTLER_EVAL_HARD_FEEDBACK_HOURS", "0")
        report = FeedbackReport(
            suggestions=[
                FeedbackSuggestion(
                    category="reliability",
                    severity="warning",
                    message="routing low",
                    metric_name="delegate_routing",
                    metric_value=0.4,
                    threshold=0.6,
                )
            ]
        )
        result = apply_hard_feedback(report)
        assert result.get("applied") is True
        overrides = load_overrides()
        assert overrides.get("delegate_routing_hint") is True
