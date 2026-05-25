"""Support line E: tool subset, implicit context, schema optimize, token diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.core.schema_optimizer import optimize_tool_definitions, schema_optimize_enabled
from butler.ops.token_cost_diagnostics import format_token_cost_diagnostic_lines
from butler.permissions import get_workflow_step_tool_allowlist
from butler.tools.project_tools import (
    filter_tool_definitions,
    intersect_allowed_names,
)
from butler.tools.tool_implicit_context import merge_implicit_tool_args


def test_intersect_workflow_and_project_tools():
    project = {"read_file", "patch", "terminal"}
    step = {"read_file", "search_files"}
    got = intersect_allowed_names(project, step)
    assert got == {"read_file"}


def test_workflow_step_allowlist_from_yaml(tmp_path: Path):
    butler = tmp_path / ".butler"
    butler.mkdir(parents=True, exist_ok=True)
    (butler / "permissions.yaml").write_text(
        "workflow_steps:\n  qa:\n    tools: [read_file, search_files]\n",
        encoding="utf-8",
    )
    allow = get_workflow_step_tool_allowlist("qa", workspace=tmp_path)
    assert allow == {"read_file", "search_files"}


def test_merge_implicit_tool_args(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_IMPLICIT_CONTEXT", "1")
    from butler.execution_context import use_execution_context

    orch_stub = type("_O", (), {"project_manager": None})()
    with use_execution_context(orch_stub, session_key="test-session-1"):
        merged = merge_implicit_tool_args({"path": "x.md"})
    assert merged["path"] == "x.md"
    assert merged.get("_butler_session_key") == "test-session-1"


def test_schema_optimizer_strips_pattern():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "d",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "q": {"type": "string", "pattern": "^[a-z]+$"},
                    },
                },
            },
        }
    ]
    out = optimize_tool_definitions(tools, diagnostics={})
    assert schema_optimize_enabled()
    assert out is not None
    props = out[0]["function"]["parameters"]["properties"]["q"]
    assert "pattern" not in props


def test_token_cost_lines():
    lines = format_token_cost_diagnostic_lines(
        {
            "context_usage_billable_total": 12000,
            "last_usage_prompt_tokens": 1000,
            "last_usage_completion_tokens": 200,
        },
        model="gpt-4",
        estimate_cost=True,
    )
    assert any("计费 tokens" in ln for ln in lines)
    assert any("粗算成本" in ln for ln in lines)


def test_filter_respects_allowlist():
    tools = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        {"type": "function", "function": {"name": "terminal", "parameters": {}}},
    ]
    filtered = filter_tool_definitions(tools, {"read_file"})
    assert len(filtered) == 1
    assert filtered[0]["function"]["name"] == "read_file"
