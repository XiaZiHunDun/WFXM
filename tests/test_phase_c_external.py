"""Phase C: scale, workflow validate, tool selector, permissions, execute_code gate."""

from __future__ import annotations

import pytest

from butler.core.loop_plugins import LoopPluginRegistry
from butler.core.tool_result_cache import (
    cache_key,
    get_cached_result,
    set_cached_result,
)
from butler.core.tool_selector import select_tools_for_context
from butler.permissions import PermissionDecision, evaluate_tool_policy
from butler.tools.execute_code import execute_code_enabled, run_execute_code
from butler.tools.provider_layers import tool_provider_layer
from butler.workflows.schema import WorkflowDef, WorkflowStepDef
from butler.workflows.validate import validate_workflow_def


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name}}


@pytest.mark.unit
def test_tool_selector_drops_when_over_threshold(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SELECTOR_THRESHOLD", "4")
    tools = [_tool(f"t{i}") for i in range(10)]
    tools.append(_tool("read_file"))
    selected, diag = select_tools_for_context(tools, user_hint="read file audit")
    assert len(selected) <= 5
    names = {t["function"]["name"] for t in selected}
    assert "read_file" in names
    assert diag["tool_selector_dropped"] >= 5


@pytest.mark.unit
def test_tool_result_cache_roundtrip():
    args = {"path": "README.md"}
    set_cached_result("read_file", args, "cached-body", session_key="sk1")
    assert get_cached_result("read_file", args, session_key="sk1") == "cached-body"
    assert get_cached_result("read_file", args, session_key="sk2") is None
    assert cache_key("read_file", args) != cache_key("read_file", {"path": "other"})


@pytest.mark.unit
def test_loop_plugin_before_model():
    class _P:
        def before_model(self, messages):
            return messages + [{"role": "system", "content": "plugin"}]

        def wrap_tool_call(self, name, args, dispatch):
            return dispatch(name, args)

    reg = LoopPluginRegistry(plugins=[_P()])
    out = reg.before_model([{"role": "user", "content": "hi"}])
    assert len(out) == 2


@pytest.mark.unit
def test_workflow_validate_cycle():
    wf = WorkflowDef(
        name="demo",
        steps=[
            WorkflowStepDef(id="a", role="dev", task="t1", depends_on=["b"]),
            WorkflowStepDef(id="b", role="dev", task="t2", depends_on=["a"]),
        ],
    )
    errors = validate_workflow_def(wf)
    assert any("cycle" in e for e in errors)


@pytest.mark.unit
def test_tool_provider_layer():
    assert tool_provider_layer("mcp_filesystem_read") == "mcp"
    assert tool_provider_layer("delegate_task") == "workflow"
    assert tool_provider_layer("read_file") == "builtin"


@pytest.mark.unit
def test_execute_code_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_EXECUTE_CODE", raising=False)
    assert not execute_code_enabled()
    out = run_execute_code("print(1)")
    assert out.get("code") == "EXECUTE_CODE_DISABLED"


@pytest.mark.unit
def test_tool_policy_ask(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    perms = tmp_path / ".butler" / "permissions.yaml"
    perms.parent.mkdir(parents=True, exist_ok=True)
    perms.write_text(
        "tool_policies:\n  write_file: ask\n",
        encoding="utf-8",
    )
    decision = evaluate_tool_policy("write_file", workspace=tmp_path)
    assert isinstance(decision, PermissionDecision)
    assert decision.action == "ask"
