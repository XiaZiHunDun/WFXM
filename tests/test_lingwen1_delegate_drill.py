"""LingWen1 isolated delegate drill workspace."""

from __future__ import annotations

from butler.ops.lingwen1_delegate_drill import setup_drill_workspace


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
