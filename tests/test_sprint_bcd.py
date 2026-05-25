"""Sprint B–D: handoff, workflow retries, MCP profiles, I/O guardrail, RAG, web_fetch."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
import yaml

from butler.core.handoff import merge_handoff_into_context, render_handoff_block
from butler.core.io_guardrail import check_inbound_text
from butler.mcp.profiles import filter_servers_by_profile, select_profile_for_text
from butler.mcp.types import McpServerConfig
from butler.workflows.loader import load_builtin_workflow
from butler.workflows.schema import parse_step


def test_render_handoff_block_contains_marker():
    block = render_handoff_block(
        from_role="dev",
        to_role="review",
        task="fix login",
        acceptance=["tests pass"],
    )
    assert "## Handoff" in block
    assert "fix login" in block


def test_merge_handoff_skips_duplicate():
    ctx = "## Handoff\n- x"
    out = merge_handoff_into_context(ctx, "## Handoff\n- y")
    assert out == ctx


def test_parse_step_max_retries():
    step = parse_step({
        "id": "qa",
        "role": "review",
        "task": "check",
        "max_retries": 3,
    })
    assert step is not None
    assert step.max_retries == 3


def test_load_dev_qa_loop_builtin():
    wf = load_builtin_workflow("dev-qa-loop")
    assert wf is not None
    assert len(wf.steps) == 2
    assert wf.steps[1].max_retries == 3
    assert "{{implement.output}}" in wf.steps[1].task


def test_io_guardrail_detects_api_key():
    with patch.dict(os.environ, {"BUTLER_IO_GUARDRAIL": "1"}, clear=False):
        r = check_inbound_text("api_key=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert r.tripwire
    assert r.reason == "secret_pattern"


def test_mcp_profile_keyword_routing():
    with patch.dict(os.environ, {"BUTLER_MCP_PROFILES": "1"}, clear=False):
        prof = select_profile_for_text("请用浏览器打开页面截图")
    assert prof in ("default", "browser", "web")


def test_filter_servers_by_profile():
    configs = [
        McpServerConfig(server_id="a", transport="stdio", command="echo"),
        McpServerConfig(server_id="b", transport="stdio", command="echo"),
    ]
    with patch("butler.mcp.profiles._ensure_loaded") as mock_load:
        mock_load.side_effect = lambda: None
        import butler.mcp.profiles as prof_mod

        prof_mod._PROFILES = {"tiny": ["a"]}
        prof_mod._ROUTING = []
        out = filter_servers_by_profile(configs, "tiny")
    assert len(out) == 1
    assert out[0].server_id == "a"


def test_web_fetch_disabled_by_default():
    from butler.tools.web_fetch import tool_web_fetch, web_fetch_enabled

    assert not web_fetch_enabled()
    raw = tool_web_fetch("https://example.com")
    data = json.loads(raw)
    assert "disabled" in data.get("error", "").lower() or data.get("error")


def test_delegate_group_id_stable():
    from butler.runtime.task_store import delegate_group_id

    a = delegate_group_id("wechat:1")
    b = delegate_group_id("wechat:1")
    assert a == b
    assert len(a) == 16


def test_corpus_route_project_keywords():
    from butler.memory.corpus_router import route_corpus_query

    r = route_corpus_query("本项目 MEMORY 里关于部署的决策")
    assert r.scope == "project"


def test_ops_checklist_builtin():
    wf = load_builtin_workflow("ops-checklist")
    assert wf is not None
    assert wf.runnable
