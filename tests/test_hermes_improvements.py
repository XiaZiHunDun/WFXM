"""Tests for toolset profiles and MCP schema normalize."""

import pytest

from butler.mcp.schema_normalize import normalize_tool_schema
from butler.skills.guard import infer_trust_level, resolve_skill_load_policy, scan_verdict
from butler.tools.toolset_profiles import filter_definitions_by_toolset


@pytest.mark.unit
def test_guard_trust_matrix():
    assert resolve_skill_load_policy("pass", "builtin") == "inject"
    assert resolve_skill_load_policy("warn", "hub") == "block"
    assert resolve_skill_load_policy("pass", "hub") == "warn_inject"


@pytest.mark.unit
def test_scan_verdict_block_injection():
    assert scan_verdict(["prompt_injection"]) == "block"


@pytest.mark.unit
def test_infer_trust_hub(tmp_path):
    p = tmp_path / "registry" / "foo.md"
    p.parent.mkdir(parents=True)
    p.write_text("---\nname: x\n---\n", encoding="utf-8")
    assert infer_trust_level(p) == "hub"


@pytest.mark.unit
def test_toolset_wechat_minimal():
    defs = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        {"type": "function", "function": {"name": "run_shell", "parameters": {}}},
    ]
    out = filter_definitions_by_toolset(defs, toolset="wechat_minimal")
    names = [d["function"]["name"] for d in out]
    assert "read_file" in names
    assert "run_shell" not in names


@pytest.mark.unit
def test_toolset_intersects_project_allowlist():
    from butler.tools.project_tools import filter_tool_definitions, intersect_allowed_names
    from butler.tools.toolset_profiles import filter_definitions_by_toolset

    defs = [
        {"type": "function", "function": {"name": n, "parameters": {}}}
        for n in ("read_file", "run_shell", "delegate_task", "butler_recall")
    ]
    toolset_filtered = filter_definitions_by_toolset(defs, toolset="wechat_minimal")
    project_allowed = intersect_allowed_names(
        {"read_file", "delegate_task", "run_shell"},
        None,
    )
    assert project_allowed is not None
    merged = filter_tool_definitions(toolset_filtered, project_allowed)
    names = {d["function"]["name"] for d in merged}
    assert "read_file" in names
    assert "delegate_task" in names
    assert "run_shell" not in names


@pytest.mark.unit
def test_normalize_double_wrap():
    wrapped = {
        "type": "function",
        "function": {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "d",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }
    out = normalize_tool_schema(wrapped)
    assert out["function"]["name"] == "demo"
    assert out["function"]["parameters"]["type"] == "object"
