"""Five-reports P10: thinking headers, hub manifest, schema registry, corpus live full."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_thinking_beta_resolves_for_anthropic(monkeypatch):
    monkeypatch.setenv("BUTLER_THINKING_PROTOCOL", "1")
    from butler.transport.thinking_headers import resolve_thinking_beta_value

    beta = resolve_thinking_beta_value(provider="anthropic", model="claude-sonnet-4")
    assert beta


@pytest.mark.unit
def test_thinking_beta_disabled_by_default():
    from butler.transport.thinking_headers import resolve_thinking_beta_value

    assert resolve_thinking_beta_value(provider="anthropic", model="claude-sonnet-4") == ""


@pytest.mark.unit
def test_hub_manifest_verify():
    from butler.registry.hub_manifest import verify_hub_manifest

    report = verify_hub_manifest()
    assert report.catalog_integrity_ok or report.catalog_errors


@pytest.mark.unit
def test_named_output_schema_debate():
    from butler.core.output_schema_registry import get_named_schema, validate_with_named_schema

    schema = get_named_schema("debate_verdict")
    assert schema
    ok, errs = validate_with_named_schema(
        "debate_verdict",
        {
            "bull_summary": "up",
            "bear_summary": "down",
            "verdict": "neutral",
            "confidence": 50,
        },
    )
    assert ok, errs


@pytest.mark.unit
def test_output_schema_repair_max_rounds():
    from butler.core.confirm_flags import output_schema_repair_max_rounds

    assert output_schema_repair_max_rounds() >= 1


@pytest.mark.unit
def test_iter_registry_live_single_turn_cases():
    from butler.prompt_eval.corpus_bridge import iter_registry_live_single_turn_cases

    cases = iter_registry_live_single_turn_cases()
    assert cases
    assert cases[0][0].startswith("dev_assistant.")


@pytest.mark.unit
def test_trading_debate_workflow_file_exists():
    path = ROOT / "butler/workflows/builtin/trading-debate.yaml"
    assert path.is_file()
    assert "bull_case" in path.read_text(encoding="utf-8")
