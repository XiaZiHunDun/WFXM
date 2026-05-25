"""Five-reports P7: install pre-scan, corpus prompt eval, injection gate."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_install_pre_scan_enabled_by_default():
    from butler.registry.install_scan import install_pre_scan_enabled

    assert install_pre_scan_enabled()


@pytest.mark.unit
def test_pre_install_scan_skill_clean_bundle():
    from butler.registry.install_scan import pre_install_scan_skill
    from butler.registry.skill_types import SkillBundle

    bundle = SkillBundle(
        name="demo",
        files={"SKILL.md": "# Demo\n\nSafe skill content."},
        source="local",
        identifier="demo",
        trust="official",
    )
    scan = pre_install_scan_skill(bundle, source="test")
    assert scan.ok_to_install
    assert scan.verdict in ("clean", "warn")


@pytest.mark.unit
def test_corpus_overlay_loads():
    from butler.prompt_eval.corpus_bridge import load_corpus_overlay

    rows = load_corpus_overlay(ROOT / "tests/fixtures/prompt_eval/corpus_cases.yaml")
    assert rows
    assert rows[0]["suite_id"] == "dev_assistant.v1"


@pytest.mark.unit
def test_corpus_prompt_subset_mock():
    from butler.prompt_eval.corpus_bridge import run_corpus_prompt_subset

    ok, errors = run_corpus_prompt_subset(
        overlay_path=ROOT / "tests/fixtures/prompt_eval/corpus_cases.yaml",
    )
    assert ok, errors


@pytest.mark.unit
def test_injection_llm_gate_disabled_by_default():
    from butler.memory.injection_llm_score import injection_llm_gate_enabled

    assert not injection_llm_gate_enabled()


@pytest.mark.unit
def test_injection_review_gate_confirm(monkeypatch, tmp_path):
    from butler import human_gate as hg
    from butler.human_gate import (
        consume_injection_bypass,
        grant_injection_bypass,
        has_injection_review_pending,
        request_injection_review_gate,
        resolve_human_gate_message,
    )

    monkeypatch.setattr(hg, "get_butler_home", lambda: tmp_path)
    sk = "wechat:test"
    request_injection_review_gate(sk, score=92)
    assert has_injection_review_pending(sk)
    reply = resolve_human_gate_message(sk, "确认")
    assert reply and "重新发送" in reply
    assert not has_injection_review_pending(sk)
    assert consume_injection_bypass(sk)


@pytest.mark.unit
def test_pre_install_scan_mcp_stdio():
    from butler.registry.install_scan import pre_install_scan_mcp
    from butler.registry.mcp_catalog import McpCatalogEntry

    entry = McpCatalogEntry(
        id="test-scan",
        title="Test",
        description="safe",
        transport="stdio",
        command="npx -y @modelcontextprotocol/server-filesystem /tmp",
        trust="official",
    )
    block = {"transport": "stdio", "command": entry.command}
    scan = pre_install_scan_mcp(entry, block)
    assert scan.verdict in ("clean", "warn", "block")
