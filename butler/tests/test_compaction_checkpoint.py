"""Tests for compaction checkpoint capture/restore."""

from __future__ import annotations

from butler.core.compaction_checkpoint import (
    capture_checkpoint,
    clear_checkpoint,
    load_checkpoint,
    restore_into_diagnostics,
)


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    monkeypatch.setattr(
        "butler.core.compaction_checkpoint._sessions_root",
        lambda: root,
    )
    sk = "wechat:test"
    capture_checkpoint(sk, model="test-model", open_todos=3, max_iterations=20)
    ckpt = load_checkpoint(sk)
    assert ckpt is not None
    assert ckpt["model"] == "test-model"
    assert ckpt["open_todos"] == 3
    diag: dict = {}
    restore_into_diagnostics(sk, diag)
    assert diag.get("compaction_checkpoint_restored") is True
    assert diag.get("compaction_checkpoint_model") == "test-model"
    clear_checkpoint(sk)
    assert load_checkpoint(sk) is None
