"""Compaction checkpoint restore ACL."""

from __future__ import annotations

from butler.core.compaction_checkpoint import capture_checkpoint, restore_into_diagnostics


def test_restore_revalidates_summary_preview(tmp_path, monkeypatch):
    sk = "wx:ckpt-acl"
    monkeypatch.setattr(
        "butler.core.compaction_checkpoint._sessions_root",
        lambda: tmp_path,
    )
    capture_checkpoint(
        sk,
        compression_summary='{"summary": "stored", "tags": ["k"]}',
    )
    diag: dict = {}
    restore_into_diagnostics(sk, diag)
    assert diag.get("compaction_checkpoint_restored") is True
    assert "stored" in str(diag.get("compaction_checkpoint_summary_preview") or "")
    assert diag.get("compaction_view_version") == "v1"
