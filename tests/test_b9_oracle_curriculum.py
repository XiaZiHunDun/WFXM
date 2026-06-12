"""Tests for B9 oracle curriculum episodes."""

from __future__ import annotations

from butler.dev_engine.b9_oracle_curriculum import (
    B9_ORACLE_EPISODES,
    export_curriculum_to_disk,
    format_curriculum_block,
    get_episode,
)


def test_tier1_episodes_exist():
    for tid in (
        "B9L_two_file_patch",
        "B9L_test_driven_add",
        "B9L_prod_no_test",
    ):
        ep = get_episode(tid)
        assert ep is not None
        assert len(ep.steps) >= 3


def test_format_curriculum_block():
    block = format_curriculum_block("B9L_two_file_patch")
    assert "<b9-curriculum>" in block
    assert "THRESHOLD" in block


def test_export_curriculum_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "butler.dev_engine.b9_oracle_curriculum.curriculum_audit_path",
        lambda: tmp_path / "b9_curriculum.json",
    )
    path = export_curriculum_to_disk()
    assert path.is_file()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["episode_count"] == len(B9_ORACLE_EPISODES)
