"""Five-reports P9: LLM prompt rubric, corpus live smoke registry, ToolsEngine SSOT."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_prompt_eval_llm_disabled_by_default():
    from butler.prompt_eval.llm_rubric import prompt_eval_llm_enabled

    assert not prompt_eval_llm_enabled()


@pytest.mark.unit
def test_prompt_eval_llm_rubric_mock(monkeypatch):
    from butler.prompt_eval.llm_rubric import score_prompt_eval_llm
    from butler.prompt_eval.runner import PromptEvalCase

    monkeypatch.setenv("BUTLER_PROMPT_EVAL_LLM", "1")
    case = PromptEvalCase(
        id="demo",
        file="butler/prompts/butler_system.md",
        must_contain=["禁止静默跳步"],
        description="system prompt quality",
    )
    text = (ROOT / "butler/prompts/butler_system.md").read_text(encoding="utf-8")
    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value='{"score": 88, "note": "ok"}',
    ):
        score, note = score_prompt_eval_llm(case, text)
    assert score == 88
    assert "ok" in note


@pytest.mark.unit
def test_iter_registry_live_smoke_cases():
    from butler.prompt_eval.corpus_bridge import iter_registry_live_smoke_cases

    cases = iter_registry_live_smoke_cases()
    assert cases
    suites = {sid for sid, _ in cases}
    assert "dev_assistant.v2" in suites


@pytest.mark.unit
def test_tools_manifest_ssot_drops_orphan_mcp(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOLS_ENGINE_SSOT", "1")
    from butler.mcp.tools_manifest import filter_tools_by_mcp_ssot

    tools = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "mcp_missing_server_tool_x"}},
    ]
    out, diag = filter_tools_by_mcp_ssot(tools, workspace=ROOT)
    names = [(t.get("function") or {}).get("name") for t in out]
    assert "read_file" in names
    assert "mcp_missing_server_tool_x" not in names
    assert diag.get("tools_manifest_dropped_mcp", 0) >= 1


@pytest.mark.unit
def test_tools_engine_applies_manifest_when_enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOLS_ENGINE_SSOT", "1")
    from butler.mcp.tools_engine import filter_tools_for_model

    tools = [
        {"type": "function", "function": {"name": "read_file"}},
        {"type": "function", "function": {"name": "mcp_orphan_x_y"}},
    ]
    out, diag = filter_tools_for_model(tools, provider="minimax", model="MiniMax-M2.7")
    names = [(t.get("function") or {}).get("name") for t in out]
    assert "read_file" in names
    assert "tools_manifest_input" in diag
