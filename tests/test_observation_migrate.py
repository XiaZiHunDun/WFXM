"""Tests for observations.tsv → observations.db migration and diagnostics."""

from __future__ import annotations

import csv
from pathlib import Path

from butler.memory.observation_migrate import (
    migrate_tsv_if_needed,
    migrate_tsv_to_db,
    observations_tsv_migrated_path,
    observations_tsv_path,
)
from butler.memory.observation_store import ObservationStore, observations_db_path
from butler.memory.observer_queue import observations_db
from butler.ops.health_report import HealthReportInput, _shared_diagnostic_lines
from butler.ops.observation_diagnostics import (
    collect_observation_store_stats,
    format_observation_diagnostic_lines,
)


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "row_id",
        "timestamp",
        "session_key",
        "tool",
        "ok",
        "path",
        "preview",
        "title",
        "content_hash",
    )
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def test_migrate_tsv_imports_when_db_empty(tmp_path):
    tsv = observations_tsv_path(tmp_path)
    _write_tsv(
        tsv,
        [
            {
                "row_id": "r1",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/a.py",
                "preview": "legacy preview",
                "title": "read_file:src/a.py",
                "content_hash": "h1",
            }
        ],
    )

    result = migrate_tsv_to_db(tmp_path)

    assert result["ok"] is True
    assert result["imported"] == 1
    assert not tsv.is_file()
    assert observations_tsv_migrated_path(tmp_path).is_file()
    rows = ObservationStore(observations_db_path(tmp_path)).list_for_path("src/a.py")
    assert len(rows) == 1
    assert rows[0]["preview"] == "legacy preview"


def test_migrate_tsv_skips_when_db_nonempty(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            {
                "row_id": "existing",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/b.py",
                "preview": "db row",
                "title": "t",
                "content_hash": "h",
            }
        ]
    )
    _write_tsv(
        observations_tsv_path(tmp_path),
        [
            {
                "row_id": "r2",
                "timestamp": "2026-05-26T00:01:00+00:00",
                "session_key": "sk",
                "tool": "grep",
                "ok": "1",
                "path": "src/c.py",
                "preview": "tsv row",
                "title": "grep:src/c.py",
                "content_hash": "h2",
            }
        ],
    )

    result = migrate_tsv_to_db(tmp_path)

    assert result["reason"] == "db_nonempty"
    assert result["imported"] == 0
    assert observations_tsv_path(tmp_path).is_file()


def test_migrate_tsv_force_merges_into_nonempty_db(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            {
                "row_id": "existing",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/b.py",
                "preview": "db row",
                "title": "t",
                "content_hash": "h",
            }
        ]
    )
    _write_tsv(
        observations_tsv_path(tmp_path),
        [
            {
                "row_id": "r2",
                "timestamp": "2026-05-26T00:01:00+00:00",
                "session_key": "sk",
                "tool": "grep",
                "ok": "1",
                "path": "src/c.py",
                "preview": "tsv row",
                "title": "grep:src/c.py",
                "content_hash": "h2",
            }
        ],
    )

    result = migrate_tsv_to_db(tmp_path, force=True)

    assert result["imported"] == 1
    stats = db.stats()
    assert stats["row_count"] == 2


def test_observations_db_auto_migrates_empty_db(tmp_path):
    _write_tsv(
        observations_tsv_path(tmp_path),
        [
            {
                "row_id": "auto",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/auto.py",
                "preview": "auto migrate",
                "title": "t",
                "content_hash": "ha",
            }
        ],
    )

    store = observations_db(tmp_path)
    rows = store.list_for_path("src/auto.py")

    assert len(rows) == 1
    assert rows[0]["row_id"] == "auto"
    again = migrate_tsv_if_needed(tmp_path, store=store)
    assert again["reason"] == "no_tsv"


def test_observation_store_stats_counts_tools(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            {
                "row_id": "r1",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "a.py",
                "preview": "p1",
                "title": "t",
                "content_hash": "h1",
            },
            {
                "row_id": "r2",
                "timestamp": "2026-05-26T00:01:00+00:00",
                "session_key": "sk",
                "tool": "grep",
                "ok": "0",
                "path": "b.py",
                "preview": "p2",
                "title": "t",
                "content_hash": "h2",
            },
        ]
    )

    stats = db.stats()

    assert stats["row_count"] == 2
    assert stats["distinct_paths"] == 2
    assert stats["ok_count"] == 1
    assert stats["fail_count"] == 1
    assert stats["tool_counts"]["read_file"] == 1
    assert stats["tool_counts"]["grep"] == 1


def test_format_observation_diagnostic_lines(tmp_path):
    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            {
                "row_id": "r1",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/x.py",
                "preview": "preview",
                "title": "t",
                "content_hash": "h",
            }
        ]
    )

    lines = format_observation_diagnostic_lines(tmp_path)
    text = "\n".join(lines)

    assert "Observation Store" in text
    assert "行数 1" in text
    assert "PreRead 排序" in text
    assert "timestamp" in text


def test_health_report_includes_observation_block(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    db = ObservationStore(observations_db_path(tmp_path))
    db.insert_many(
        [
            {
                "row_id": "r1",
                "timestamp": "2026-05-26T00:00:00+00:00",
                "session_key": "sk",
                "tool": "read_file",
                "ok": "1",
                "path": "src/x.py",
                "preview": "preview",
                "title": "t",
                "content_hash": "h",
            }
        ]
    )

    proj = MagicMock()
    proj.workspace = tmp_path
    proj.name = "test"
    proj.type = ""
    orch = MagicMock()
    orch.project_manager.get_current.return_value = proj
    orch.project_manager.resolve_active_project_name.return_value = "test"
    orch._settings = MagicMock()

    lines = _shared_diagnostic_lines(
        HealthReportInput(
            session_key="sk",
            health={},
            tool_summary={},
            mem_stats={},
            orchestrator=orch,
        )
    )
    text = "\n".join(lines)

    assert "Observation Store" in text
    assert "行数 1" in text


def test_collect_observation_store_stats_flags_legacy_tsv(tmp_path):
    observations_tsv_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    observations_tsv_path(tmp_path).write_text("row_id\ttimestamp\n", encoding="utf-8")

    stats = collect_observation_store_stats(tmp_path)

    assert stats["tsv_exists"] is True
    assert stats["row_count"] == 0
