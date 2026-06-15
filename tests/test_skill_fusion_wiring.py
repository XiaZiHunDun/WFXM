"""Skill fusion wiring tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.skills.fusion_wiring import skill_fusion_enabled, wire_skill_manager_fusion


@pytest.mark.unit
def test_wire_skill_manager_fusion_sets_llm(monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_FUSION", "1")
    mgr = MagicMock()
    wire_skill_manager_fusion(mgr)
    mgr.set_llm_fn.assert_called_once()


@pytest.mark.unit
def test_skill_fusion_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_FUSION", "0")
    assert skill_fusion_enabled() is False
