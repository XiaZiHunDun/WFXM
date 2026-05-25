"""PR-X5/X6: exp_cache, BM25 recall, schema validate, workflow parallel/import."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.core.exp_cache import (
    fingerprint_llm_request,
    lookup_cached_response,
    store_cached_response,
)
from butler.core.meta_flags import (
    exp_cache_enabled,
    tool_recall_bm25_enabled,
    workflow_checkpoint_enabled,
)
from butler.core.tool_recall_bm25 import rank_tools_bm25
from butler.core.tool_selector import select_tools_for_context
from butler.report import (
    AgentReport,
    enrich_output_schema,
    validate_structured_output,
)
from butler.task_orchestrator import _group_into_layers
from butler.workflows.loader import _merge_imported_steps
from butler.workflows.schema import parse_workflow_data, WorkflowDef, WorkflowStepDef


def test_fingerprint_stable():
    fp1 = fingerprint_llm_request(
        provider="openai",
        model="gpt",
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
    )
    fp2 = fingerprint_llm_request(
        provider="openai",
        model="gpt",
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
    )
    assert fp1 == fp2


def test_exp_cache_store_and_lookup(monkeypatch):
    monkeypatch.setenv("BUTLER_EXP_CACHE", "1")
    assert exp_cache_enabled()
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / ".butler" / "experiences").mkdir(parents=True)
        proj = type("P", (), {"workspace": ws})()
        orch = type("O", (), {"project_manager": type("PM", (), {
            "get_current": lambda self, session_key="": proj,
        })()})()
        fp = "test_fp_abc"
        with patch("butler.execution_context.get_current_orchestrator", return_value=orch):
            with patch("butler.execution_context.get_current_session_key", return_value="s1"):
                store_cached_response(fp, "cached answer", provider="p", model="m")
                assert lookup_cached_response(fp) == "cached answer"


def test_bm25_ranks_matching_tool():
    tools = [
        {"type": "function", "function": {"name": "read_file", "description": "read bytes"}},
        {"type": "function", "function": {"name": "terminal", "description": "run shell"}},
    ]
    ranked = rank_tools_bm25(tools, "read file content", top_k=1)
    assert ranked[0]["function"]["name"] == "read_file"


def test_tool_selector_uses_bm25_when_enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_RECALL_BM25", "1")
    monkeypatch.setenv("BUTLER_TOOL_SELECTOR", "1")
    monkeypatch.setenv("BUTLER_TOOL_SELECTOR_THRESHOLD", "4")
    assert tool_recall_bm25_enabled()
    tools = [
        {"type": "function", "function": {"name": f"tool_{i}", "description": f"desc {i}"}}
        for i in range(6)
    ]
    tools[4] = {
        "type": "function",
        "function": {"name": "beta_search_tool", "description": "beta search indexer"},
    }
    chosen, diag = select_tools_for_context(tools, user_hint="search beta")
    assert len(chosen) == 4
    assert diag.get("tool_recall_bm25_output") == 4
    names = [t["function"]["name"] for t in chosen]
    assert "beta_search_tool" in names


def test_validate_structured_output_required_field():
    ok, errs = validate_structured_output(
        {"rating": "approve"},
        {"fields": [{"name": "rating", "type": "string", "required": True}, {"name": "score", "type": "integer", "required": True}]},
    )
    assert not ok
    assert any("score" in e for e in errs)


def test_enrich_output_schema_adds_issues_on_invalid():
    report = AgentReport()
    enrich_output_schema(
        report,
        '{"rating": "approve"}',
        {"fields": [{"name": "rating", "type": "string"}, {"name": "score", "type": "integer", "required": True}]},
    )
    assert report.structured_output
    assert report.issues


def test_parse_workflow_max_parallel_and_serial():
    wf = parse_workflow_data({
        "name": "demo",
        "max_parallel": 2,
        "serial": True,
        "steps": [{"id": "a", "role": "dev", "task": "t"}],
    })
    assert wf is not None
    assert wf.max_parallel == 2
    assert wf.serial is True


def test_merge_imported_steps():
    imp_step = WorkflowStepDef(id="prep", role="dev", task="prepare")
    imported = WorkflowDef(name="base", steps=[imp_step])
    local = WorkflowDef(
        name="child",
        steps=[WorkflowStepDef(id="run", role="dev", task="go")],
        imports=["base"],
    )
    proj = type("P", (), {"workspace": Path("/tmp")})()
    with patch("butler.workflows.loader.load_workspace_workflow", return_value=None):
        with patch("butler.workflows.loader.load_builtin_workflow", return_value=imported):
            merged = _merge_imported_steps(proj, local)
    assert [s.id for s in merged.steps] == ["prep", "run"]


def test_group_into_layers():
    nodes = [
        type("N", (), {"id": "a", "depends_on": []})(),
        type("N", (), {"id": "b", "depends_on": ["a"]})(),
    ]
    node_map = {n.id: n for n in nodes}
    layers = _group_into_layers(["a", "b"], node_map)
    assert layers == [["a"], ["b"]]


def test_workflow_checkpoint_flag_default():
    assert workflow_checkpoint_enabled()
