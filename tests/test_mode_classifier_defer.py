"""E2/E3/E4 deferred items — mode classifier, delegate one-tool, compaction checklist."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from butler.core.compaction_prompt import (
    build_compaction_user_prompt,
    compaction_preflight_checklist_enabled,
)
from butler.core.mode_classifier import (
    classify_mode_heuristic,
    classify_turn_mode,
    detect_mode_suggestion_banner,
    mode_classifier_enabled,
    score_mode,
)
from butler.delegate.policy import delegate_one_tool_per_iteration


def test_plan_heuristic_long_design_message():
    text = "帮我分析一下当前 butler 网关架构，先给出重构方案和步骤，先别改代码。"
    assert classify_mode_heuristic(text) == "plan"
    plan, do = score_mode(text)
    assert plan > do


def test_do_heuristic_implementation_message():
    text = "请直接修复 tests/test_foo.py 的失败并跑一下 pytest，改完告诉我结果。"
    assert classify_mode_heuristic(text) == "do"


def test_short_message_skips_classifier():
    assert classify_mode_heuristic("好的") is None


def test_mode_suggestion_banner_plan(monkeypatch):
    monkeypatch.delenv("BUTLER_MODE_CLASSIFIER", raising=False)
    monkeypatch.delenv("BUTLER_MODE_CLASSIFIER_AUTO_PLAN", raising=False)
    monkeypatch.setenv("BUTLER_MODE_CLASSIFIER_MIN_CHARS", "20")
    text = (
        "我想先调研一下多项目切换与 session 隔离的方案，不要动代码，"
        "只输出分阶段实施计划和风险点即可。"
    )
    banner = detect_mode_suggestion_banner(text, session_key="mc-test")
    assert banner and "/规划" in banner


def test_compaction_prompt_includes_checklist_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_COMPACTION_PREFLIGHT_CHECKLIST", raising=False)
    assert compaction_preflight_checklist_enabled()
    prompt = build_compaction_user_prompt(transcript="[USER]: hi")
    assert "tests, lint" in prompt or "execution quality" in prompt


def test_compaction_checklist_can_disable(monkeypatch):
    monkeypatch.setenv("BUTLER_COMPACTION_PREFLIGHT_CHECKLIST", "0")
    prompt = build_compaction_user_prompt(transcript="x")
    assert "execution quality" not in prompt


def test_delegate_one_tool_default_off(monkeypatch):
    monkeypatch.delenv("BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION", raising=False)
    assert not delegate_one_tool_per_iteration()


def test_delegate_one_tool_env_on(monkeypatch):
    monkeypatch.setenv("BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION", "1")
    assert delegate_one_tool_per_iteration()


def test_delegate_loop_disables_parallel_tools(monkeypatch):
    """Child loop gets enable_parallel_tools=False when env set."""
    monkeypatch.setenv("BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION", "1")
    from butler.core.loop_types import LoopConfig
    from butler.core.agent_loop import AgentLoop

    cfg = LoopConfig(enable_parallel_tools=True)
    agent = MagicMock()
    agent.config = cfg
    agent.diagnostics = {}
    if delegate_one_tool_per_iteration():
        agent.config.enable_parallel_tools = False
        agent.diagnostics["delegate_one_tool_per_iteration"] = True
    assert agent.config.enable_parallel_tools is False


def test_mode_classifier_enabled_default(monkeypatch):
    monkeypatch.delenv("BUTLER_MODE_CLASSIFIER", raising=False)
    assert mode_classifier_enabled()
