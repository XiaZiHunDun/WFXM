"""Unit tests for SQLite-backed observation store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from butler.execution_context import use_execution_context
from butler.memory.observer_queue import (
    clear_observer_queue,
    enqueue_tool_observation,
    flush_all_observer_queues,
    flush_observer_queue,
    list_observations_for_path,
)
from butler.memory.observation_store import ObservationStore, observations_db_path


def _row(
    *,
    row_id: str,
    timestamp: str,
    path: str,
    preview: str,
    tool: str = "read_file",
    content_hash: str = "",
) -> dict[str, str]:
    return {
        "row_id": row_id,
        "timestamp": timestamp,
        "session_key": "sk1",
        "tool": tool,
        "ok": "1",
        "path": path,
        "preview": preview,
        "title": f"{tool}:{path}",
        "content_hash": content_hash,
    }


def _orchestrator_for_workspace(workspace: Path):
    class _ProjectManager:
        def get_current(self, session_key: str = ""):
            del session_key
            return SimpleNamespace(workspace=workspace)

    return SimpleNamespace(project_manager=_ProjectManager())


def test_observation_store_inserts_and_queries_by_path(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            _row(
                row_id="r1",
                timestamp="2026-05-26T00:00:00+00:00",
                path="src/foo.py",
                preview="first preview",
            )
        ]
    )

    rows = db.list_for_path("src/foo.py", limit=5)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "r1"
    assert rows[0]["preview"] == "first preview"


def test_observation_store_returns_latest_matches_in_chronological_order(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            _row(
                row_id="r1",
                timestamp="2026-05-26T00:00:00+00:00",
                path="src/foo.py",
                preview="first preview",
            ),
            _row(
                row_id="r2",
                timestamp="2026-05-26T00:01:00+00:00",
                path="src/foo.py",
                preview="second preview",
            ),
            _row(
                row_id="r3",
                timestamp="2026-05-26T00:02:00+00:00",
                path="src/foo.py",
                preview="third preview",
            ),
        ]
    )

    rows = db.list_for_path("src/foo.py", limit=2)

    assert [row["row_id"] for row in rows] == ["r2", "r3"]
    assert [row["preview"] for row in rows] == ["second preview", "third preview"]


def test_observation_store_dedupes_same_session_tool_path_and_hash(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            _row(
                row_id="r1",
                timestamp="2026-05-26T00:00:00+00:00",
                path="src/foo.py",
                preview="first preview",
                content_hash="same",
            ),
            _row(
                row_id="r2",
                timestamp="2026-05-26T00:01:00+00:00",
                path="src/foo.py",
                preview="second preview",
                content_hash="same",
            ),
        ]
    )

    rows = db.list_for_path("src/foo.py", limit=5)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "r2"
    assert rows[0]["preview"] == "second preview"


def test_observation_store_migrates_existing_duplicate_rows_before_unique_index(tmp_path):
    db_path = observations_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE observations (
                row_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                session_key TEXT NOT NULL DEFAULT '',
                tool TEXT NOT NULL DEFAULT '',
                ok INTEGER NOT NULL DEFAULT 0,
                path TEXT NOT NULL DEFAULT '',
                preview TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO observations(row_id, timestamp, session_key, tool, ok, path, preview, title, content_hash)
            VALUES
                ('r1', '2026-05-26T00:00:00+00:00', 'sk1', 'read_file', 1, 'src/foo.py', 'old', 'read_file:src/foo.py', 'same'),
                ('r2', '2026-05-26T00:01:00+00:00', 'sk1', 'read_file', 1, 'src/foo.py', 'new', 'read_file:src/foo.py', 'same');
            """
        )
        conn.commit()

    db = ObservationStore(db_path)
    rows = db.list_for_path("src/foo.py", limit=5)

    assert len(rows) == 1
    assert rows[0]["row_id"] == "r2"
    assert rows[0]["preview"] == "new"


def test_observation_store_prunes_rows_older_than_ttl(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_TTL_DAYS", "7")
    db = ObservationStore(observations_db_path(tmp_path))
    now = datetime.now(timezone.utc)
    db.insert_many(
        [
            _row(
                row_id="r1",
                timestamp=(now - timedelta(days=30)).isoformat(),
                path="src/foo.py",
                preview="old preview",
                content_hash="old",
            ),
            _row(
                row_id="r2",
                timestamp=now.isoformat(),
                path="src/foo.py",
                preview="new preview",
                content_hash="new",
            ),
        ]
    )

    rows = db.list_for_path("src/foo.py", limit=5)

    assert [row["row_id"] for row in rows] == ["r2"]


def test_observation_store_prunes_rows_by_max_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_MAX_ROWS", "2")
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            _row(
                row_id="r1",
                timestamp="2026-05-26T00:00:00+00:00",
                path="src/foo.py",
                preview="first preview",
                content_hash="h1",
            ),
            _row(
                row_id="r2",
                timestamp="2026-05-26T00:01:00+00:00",
                path="src/foo.py",
                preview="second preview",
                content_hash="h2",
            ),
            _row(
                row_id="r3",
                timestamp="2026-05-26T00:02:00+00:00",
                path="src/foo.py",
                preview="third preview",
                content_hash="h3",
            ),
        ]
    )

    rows = db.list_for_path("src/foo.py", limit=5)

    assert [row["row_id"] for row in rows] == ["r2", "r3"]


def test_observer_queue_is_sharded_by_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVER_QUEUE", "1")
    clear_observer_queue()
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()

    with use_execution_context(_orchestrator_for_workspace(ws1), session_key="sk1"):
        enqueue_tool_observation(
            session_key="sk1",
            tool="read_file",
            ok=True,
            preview="first workspace row",
            path="src/a.py",
        )
    with use_execution_context(_orchestrator_for_workspace(ws2), session_key="sk2"):
        enqueue_tool_observation(
            session_key="sk2",
            tool="read_file",
            ok=True,
            preview="second workspace row",
            path="src/b.py",
        )

    assert flush_observer_queue(ws2) == 1
    assert list_observations_for_path(ws1, "src/a.py", limit=5) == []
    assert [row["preview"] for row in list_observations_for_path(ws2, "src/b.py", limit=5)] == [
        "second workspace row"
    ]
    assert flush_observer_queue(ws1) == 1
    assert [row["preview"] for row in list_observations_for_path(ws1, "src/a.py", limit=5)] == [
        "first workspace row"
    ]


def test_flush_all_observer_queues_flushes_pending_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVER_QUEUE", "1")
    clear_observer_queue()
    ws = tmp_path / "ws"
    ws.mkdir()

    with use_execution_context(_orchestrator_for_workspace(ws), session_key="sk"):
        enqueue_tool_observation(
            session_key="sk",
            tool="read_file",
            ok=True,
            preview="pending row",
            path="src/c.py",
        )

    assert flush_all_observer_queues() == 1
    assert [row["preview"] for row in list_observations_for_path(ws, "src/c.py", limit=5)] == [
        "pending row"
    ]
