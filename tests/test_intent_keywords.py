"""Tests for intent keyword banners."""

from __future__ import annotations

from butler.core.intent_keywords import (
    category_from_intent,
    detect_intent_banner,
    intent_keywords_enabled,
)


def test_detect_ultrawork_banner(monkeypatch):
    monkeypatch.delenv("BUTLER_INTENT_KEYWORDS_OFF", raising=False)
    banner = detect_intent_banner("请全力完成这个任务 ulw")
    assert banner is not None
    assert "ultrawork" in banner.lower() or "全力" in banner


def test_category_from_intent():
    assert category_from_intent("ultrawork now") == "quick"
    assert category_from_intent("深审一下") == "ultrabrain"


def test_disabled_when_off(monkeypatch):
    monkeypatch.setenv("BUTLER_INTENT_KEYWORDS_OFF", "1")
    assert not intent_keywords_enabled()
    assert detect_intent_banner("ulw") is None
