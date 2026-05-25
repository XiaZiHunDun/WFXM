"""External-agent roadmap P1–P4 follow-up tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from butler.core.loop_middleware import LoopMiddlewareChain
from butler.core.plan_snapshot import qa_response_is_fail, replan_implement_task
from butler.core.prompt_renderer import render_orchestrator_turn
from butler.core.transcript_retention import transcript_keep_priority, transcript_source_boost
from butler.project_plugins import apply_project_plugins, normalize_plugins
from butler.project import Project
from butler.workflows.artifact_paths import artifacts_dir, requirements_path


def test_normalize_plugins_dict():
    raw = {"BUTLER_EXP_CACHE": "1", "noise": "x"}
    assert normalize_plugins(raw) == {"BUTLER_EXP_CACHE": "1"}


def test_apply_project_plugins_env_wins(monkeypatch):
    monkeypatch.setenv("BUTLER_EXP_CACHE", "0")
    proj = Project(
        name="t",
        type="software",
        description="",
        plugins={"BUTLER_EXP_CACHE": "1", "BUTLER_MCP_DEFERRED_TOOLS": "1"},
    )
    applied = apply_project_plugins(proj)
    assert "BUTLER_EXP_CACHE" not in applied
    assert os.environ.get("BUTLER_EXP_CACHE") == "0"
    assert applied.get("BUTLER_MCP_DEFERRED_TOOLS") == "1"


def test_loop_middleware_before_llm():
    class _Mw:
        def before_llm(self, messages):
            return messages + [{"role": "system", "content": "mw"}]

    chain = LoopMiddlewareChain(middlewares=[_Mw()])
    out = chain.before_llm([{"role": "user", "content": "hi"}])
    assert len(out) == 2


def test_transcript_source_boost():
    assert transcript_source_boost("delegate") > transcript_source_boost("loop")
    assert transcript_keep_priority("tool_action", source="workflow") > transcript_keep_priority(
        "tool_action", source="loop"
    )


def test_qa_fail_helpers():
    assert qa_response_is_fail("FAIL: missing tests")
    assert not qa_response_is_fail("PASS ok")
    task = replan_implement_task("do work", "FAIL: fix tests", attempt=1)
    assert "QA 未通过" in task


def test_artifact_paths(tmp_path: Path):
    root = artifacts_dir(tmp_path)
    assert root.name == "artifacts"
    assert requirements_path(tmp_path).name == "REQUIREMENTS.md"


def test_render_orchestrator_turn_no_recursion():
    class _Orch:
        def build_static_system_prompt(self):
            return "static"

        def build_dynamic_system_reminder(self, for_role="default"):
            return "dyn"

        def _assemble_default_system_prompt(self, for_role="default"):
            return "merged"

        def build_system_prompt(self):
            raise AssertionError("should not recurse")

    static, reminder = render_orchestrator_turn(_Orch(), for_role="default")
    assert static == "merged"
    assert reminder is None
