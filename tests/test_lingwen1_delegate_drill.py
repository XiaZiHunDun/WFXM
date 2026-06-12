"""LingWen1 isolated delegate drill workspace."""

from __future__ import annotations

from butler.ops.lingwen1_delegate_drill import (
    LINGWEN_DRILL_PLAYBOOK,
    build_lingwen_drill_context,
    setup_drill_workspace,
)


def test_setup_drill_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "butler.ops.lingwen1_delegate_drill.drill_workspace_path",
        lambda: tmp_path / "drill",
    )
    ws = setup_drill_workspace(force=True)
    assert (ws / "demo" / "hello.py").is_file()
    assert (ws / "test_drill.py").is_file()
    text = (ws / "demo" / "hello.py").read_text(encoding="utf-8")
    assert "a - b" in text


def test_build_lingwen_drill_context_includes_playbook(tmp_path):
    ctx = build_lingwen_drill_context(workspace=tmp_path / "ws")
    assert "patch demo/hello.py ONLY" in ctx
    assert LINGWEN_DRILL_PLAYBOOK.splitlines()[0] in ctx
    assert "Do NOT write_file" in ctx


def test_lingwen_drill_category_denies_write_file():
    from butler.delegate.category_resolver import resolve_category

    preset = resolve_category("lingwen-drill")
    assert preset is not None
    assert "write_file" in (preset.get("deny_tools") or [])
