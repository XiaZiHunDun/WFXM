"""Tests for trusted fusion model routing."""

from __future__ import annotations

import pytest

from butler.config import reload_butler_settings
from butler.transport.fusion_client import resolve_fusion_config


@pytest.mark.unit
def test_resolve_fusion_prefers_auxiliary_fusion_block(monkeypatch, tmp_butler_home):
    cfg_path = tmp_butler_home / "config.yaml"
    cfg_path.write_text(
        """
default_provider: minimax
auxiliary:
  compression:
    provider: deepseek
    model: deepseek-chat
  fusion:
    provider: minimax
    model: MiniMax-M2.7-trusted
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    reload_butler_settings()

    cfg = resolve_fusion_config()
    assert cfg.provider == "minimax"
    assert "trusted" in cfg.model or cfg.model == "MiniMax-M2.7-trusted"


@pytest.mark.unit
def test_resolve_fusion_falls_back_to_butler(monkeypatch, tmp_butler_home):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7")
    reload_butler_settings()

    cfg = resolve_fusion_config()
    assert cfg.provider == "minimax"
    assert cfg.model == "MiniMax-M2.7"
