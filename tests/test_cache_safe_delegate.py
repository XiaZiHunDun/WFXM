"""Cache-safe delegate system prompt prefix (P2)."""

from __future__ import annotations

from butler.core.cache_safe_delegate import (
    apply_cache_safe_system_prompt,
    cache_safe_delegate_enabled,
    delegate_diagnostics,
    extract_shared_prefix,
)


def test_extract_shared_prefix_truncates():
    parent = "A" * 5000
    prefix = extract_shared_prefix(parent, max_chars=100)
    assert len(prefix) == 100


def test_apply_prepends_when_missing(monkeypatch):
    monkeypatch.setenv("BUTLER_CACHE_SAFE_DELEGATE", "1")
    parent = "SHARED\n" + ("x" * 200)
    child = "child-only instructions"
    merged = apply_cache_safe_system_prompt(parent, child)
    assert merged.startswith("SHARED")
    assert "child-only" in merged
    assert cache_safe_delegate_enabled()


def test_apply_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_CACHE_SAFE_DELEGATE", "0")
    child = "only child"
    assert apply_cache_safe_system_prompt("parent", child) == child


def test_apply_skips_duplicate_prefix(monkeypatch):
    monkeypatch.setenv("BUTLER_CACHE_SAFE_DELEGATE", "1")
    prefix = extract_shared_prefix("hello parent")
    child = f"{prefix}\n\nalready merged"
    assert apply_cache_safe_system_prompt("hello parent", child) == child.strip()


def test_delegate_diagnostics_keys():
    diag = delegate_diagnostics("parent", "child")
    assert diag["cache_safe_delegate"] is True
    assert "parent_system_fingerprint" in diag
    assert diag["shared_prefix_chars"] > 0
