"""Tests for auxiliary model routing (default MiniMax when both keys present)."""

from __future__ import annotations

import pytest

from butler.config import reload_butler_settings
from butler.transport.auxiliary_client import resolve_auxiliary_config


@pytest.mark.unit
class TestAuxiliaryDefaults:
    def test_prefers_minimax_when_both_providers_configured(self, monkeypatch, tmp_butler_home):
        monkeypatch.setenv("MINIMAX_API_KEY", "minimax-key")
        monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
        monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
        reload_butler_settings()

        for task in ("compression", "post_session", "skill_consolidation"):
            cfg = resolve_auxiliary_config(task)
            assert cfg.provider == "minimax"
            assert cfg.model == "MiniMax-M2.7"
