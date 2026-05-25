"""Tests for rules engine glob triggers."""

from __future__ import annotations

from butler.core.rules_engine import resolve_rules_for_path


def test_rules_always_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_RULES_ENGINE", "1")
    rules_dir = tmp_path / ".butler" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "global.md").write_text(
        "---\nalwaysApply: true\ntitle: Global\n---\nAlways follow this.",
        encoding="utf-8",
    )
    trigger = tmp_path / "src" / "app.py"
    trigger.parent.mkdir(parents=True)
    trigger.write_text("x = 1\n", encoding="utf-8")
    block = resolve_rules_for_path(trigger, workspace_root=tmp_path)
    assert "Global" in block
    assert "Always follow" in block
