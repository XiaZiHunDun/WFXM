"""Memory hygiene phase B: vector sync on prune/delete + butler memory gc."""

from __future__ import annotations

import time

import pytest

from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_index import SOURCE_EXPERIENCE


@pytest.mark.module_test
class TestConversationPurgeVectorSync:
    def test_prune_deletes_matching_experience_vectors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        monkeypatch.setenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "0")

        bm = ButlerMemory(tmp_path / "home")
        assert bm.semantic is not None
        sem = bm.semantic

        old = time.time() - 40 * 86400
        with bm.experience._lock:
            conn = bm.experience._conn
            conn.execute(
                """
                INSERT INTO experiences (project, category, content, tags, created_at)
                VALUES ('', 'conversation', 'old echo', 'session:x', ?)
                """,
                (old,),
            )
            row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.commit()

        # upsert() skips conversation category; insert stale vector directly.
        with sem._lock:
            sem._conn.execute(
                """
                INSERT INTO memory_vectors (
                    source, source_id, project, category, content,
                    embedding_json, model_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    SOURCE_EXPERIENCE,
                    str(row_id),
                    "",
                    "conversation",
                    "old echo vector",
                    "[]",
                    sem.model_id,
                    time.time(),
                ),
            )
            sem._conn.commit()
        assert sem.count_by_source(SOURCE_EXPERIENCE) == 1

        result = bm.prune_conversation_older_than(30)
        assert result["removed_rows"] == 1
        assert result["removed_vectors"] == 1
        assert sem.count_by_source(SOURCE_EXPERIENCE) == 0

    def test_delete_session_syncs_vectors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        monkeypatch.setenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "0")

        bm = ButlerMemory(tmp_path / "home")
        assert bm.semantic is not None
        row_id = bm.experience.add(
            "",
            "conversation",
            "Q: hi → A: ok",
            tags="session:wechat:u1",
        )
        with bm.semantic._lock:
            bm.semantic._conn.execute(
                """
                INSERT INTO memory_vectors (
                    source, source_id, project, category, content,
                    embedding_json, model_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    SOURCE_EXPERIENCE,
                    str(row_id),
                    "",
                    "conversation",
                    "Q: hi → A: ok",
                    "[]",
                    bm.semantic.model_id,
                    time.time(),
                ),
            )
            bm.semantic._conn.commit()

        result = bm.delete_conversation_for_session("session:wechat:u1")
        assert result["removed_rows"] == 1
        assert result["removed_vectors"] == 1
        with bm.semantic._lock:
            row = bm.semantic._conn.execute(
                "SELECT 1 FROM memory_vectors WHERE source = ? AND source_id = ?",
                (SOURCE_EXPERIENCE, str(row_id)),
            ).fetchone()
        assert row is None


@pytest.mark.module_test
class TestMemoryGcCli:
    def test_gc_dry_run_and_apply(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        monkeypatch.setenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "0")

        home = tmp_path / "home"
        bm = ButlerMemory(home)
        assert bm.semantic is not None
        sem = bm.semantic

        row_id = bm.experience.add("p", "ops", "keep me")
        deleted_id = bm.experience.add("p", "ops", "deleted row")
        with bm.experience._lock:
            bm.experience._conn.execute(
                "DELETE FROM experiences WHERE id = ?",
                (deleted_id,),
            )
            bm.experience._conn.commit()

        sem.upsert(
            source=SOURCE_EXPERIENCE,
            source_id=str(row_id),
            content="keep me",
            project="p",
            category="ops",
        )
        sem.upsert(
            source=SOURCE_EXPERIENCE,
            source_id=str(deleted_id),
            content="orphan",
            project="p",
            category="ops",
        )
        sem.upsert(
            source=SOURCE_EXPERIENCE,
            source_id="99999",
            content="another orphan",
            project="p",
            category="ops",
        )

        from butler.memory.vector_gc import run_memory_gc

        dry = run_memory_gc(home, apply=False)
        assert dry["ok"] is True
        assert dry["dry_run"] is True
        assert dry["orphan_experience_vectors"] == 2
        assert sem.count_by_source(SOURCE_EXPERIENCE) == 3

        applied = run_memory_gc(home, apply=True)
        assert applied["deleted_orphan_vectors"] == 2
        assert sem.count_by_source(SOURCE_EXPERIENCE) == 1
