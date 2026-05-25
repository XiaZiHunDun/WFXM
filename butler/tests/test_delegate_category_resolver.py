"""Tests for delegate category resolver."""

from __future__ import annotations

from butler.delegate_category_resolver import apply_category_to_delegate, list_categories


def test_list_categories_includes_presets():
    cats = list_categories()
    assert "quick" in cats
    assert "deep" in cats


def test_apply_category_overrides_role_and_task():
    role, task, ctx, meta = apply_category_to_delegate(
        category="ultrabrain",
        role="dev",
        task="analyze code",
        context="",
    )
    assert meta.get("resolved") is True
    assert role == "review"
    assert "category:ultrabrain" in task
    assert ctx == ""
