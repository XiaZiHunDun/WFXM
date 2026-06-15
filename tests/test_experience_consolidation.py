"""Experience write-path digestion tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.memory.butler_memory import ButlerMemory
from butler.memory.experience_consolidation import (
    digest_experience_add,
    experience_merge_enabled,
    load_merge_pending,
    queue_merge_pending,
)


@pytest.mark.unit
def test_digest_appends_when_merge_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE", "0")
    bm = ButlerMemory(tmp_path / "bh")
    rid = digest_experience_add(bm, "p1", "note", "first experience bullet here")
    assert rid > 0


@pytest.mark.unit
def test_digest_queues_pending_on_high_similarity(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE", "1")
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE_AUTO", "0.99")
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE_REVIEW", "0.5")
    bm = ButlerMemory(tmp_path / "bh")
    existing_id = bm._append_experience_row("p1", "note", "workflow patch status OPEN_FIX")

    with patch(
        "butler.memory.experience_consolidation.find_similar_experience",
        return_value=(
            {"id": existing_id, "content": "workflow patch status OPEN_FIX"},
            0.88,
        ),
    ):
        with patch(
            "butler.memory.experience_consolidation.fusion_merge_experience_text",
            return_value={"content": "merged", "tags": "", "fallback_used": True},
        ):
            rid = digest_experience_add(bm, "p1", "note", "workflow patch status PASSED")
    assert rid == 0
    assert load_merge_pending()


@pytest.mark.unit
def test_digest_auto_merges_when_fusion_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE", "1")
    monkeypatch.setenv("BUTLER_EXPERIENCE_MERGE_AUTO", "0.8")
    bm = ButlerMemory(tmp_path / "bh")
    existing_id = bm._append_experience_row("p1", "note", "status OPEN_FIX")

    with patch(
        "butler.memory.experience_consolidation.find_similar_experience",
        return_value=({"id": existing_id, "content": "status OPEN_FIX"}, 0.95),
    ):
        with patch(
            "butler.memory.experience_consolidation.fusion_merge_experience_text",
            return_value={"content": "status PASSED", "tags": "ops", "fallback_used": False},
        ):
            rid = digest_experience_add(bm, "p1", "note", "status OPEN_FIX variant")
    assert rid == existing_id
    row = bm.experience.search("PASSED", project="p1", limit=1)[0]
    assert "PASSED" in row["content"]


@pytest.mark.unit
def test_experience_merge_enabled_default():
    assert experience_merge_enabled() is True


@pytest.mark.unit
def test_apply_merge_pending_updates_row(monkeypatch, tmp_path):
    from butler.memory.experience_consolidation import (
        apply_merge_pending,
        load_merge_pending,
        queue_merge_pending,
    )

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "bh"))
    bm = ButlerMemory(tmp_path / "bh")
    row_id = bm._append_experience_row("p1", "note", "status OPEN_FIX")
    key = queue_merge_pending(
        existing_id=row_id,
        existing_content="status OPEN_FIX",
        new_content="status PASSED",
        project="p1",
        category="note",
        similarity=0.86,
        proposed={"content": "status OPEN_FIX → PASSED", "tags": "ops"},
    )
    bm.close()

    result = apply_merge_pending(key, butler_home=tmp_path / "bh")
    assert result.get("ok") is True
    assert not load_merge_pending()

    bm2 = ButlerMemory(tmp_path / "bh")
    row = bm2.experience.search("PASSED", project="p1", limit=1)[0]
    assert "PASSED" in row["content"]
    bm2.close()


@pytest.mark.unit
def test_dismiss_merge_pending(monkeypatch, tmp_path):
    from butler.memory.experience_consolidation import dismiss_merge_pending, load_merge_pending

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "bh"))
    key = queue_merge_pending(
        existing_id=1,
        existing_content="a",
        new_content="b",
        project="p",
        category="c",
        similarity=0.8,
    )
    assert load_merge_pending()
    result = dismiss_merge_pending(key)
    assert result.get("ok") is True
    assert not load_merge_pending()
