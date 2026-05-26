"""Unit tests for SQLite-backed observation store."""

from __future__ import annotations

from pathlib import Path

from butler.memory.observation_store import ObservationStore, observations_db_path


def _row(*, row_id: str, timestamp: str, path: str, preview: str, tool: str = "read_file") -> dict[str, str]:
    return {
        "row_id": row_id,
        "timestamp": timestamp,
        "session_key": "sk1",
        "tool": tool,
        "ok": "1",
        "path": path,
        "preview": preview,
        "title": f"{tool}:{path}",
    }


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
