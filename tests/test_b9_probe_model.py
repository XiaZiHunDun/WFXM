"""Tests for temporary_model_override used in B9 model probe."""

from __future__ import annotations

from butler.model_resolve import (
    normalize_role,
    parse_model_spec,
    resolve_effective_model,
    temporary_model_override,
)


def test_temporary_model_override_dev_agent():
    from butler.config import get_butler_settings

    settings = get_butler_settings()
    role = normalize_role("dev")
    before = dict(settings._runtime_model_overrides)
    with temporary_model_override("deepseek/deepseek-chat", role="dev"):
        eff = resolve_effective_model(role)
        assert eff.config.provider == "deepseek"
        assert eff.config.model == "deepseek-chat"
        assert "runtime" in eff.sources
    assert settings._runtime_model_overrides.get(role) == before.get(role)
