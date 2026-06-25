"""One-shot migration: legacy ``observations.tsv`` → SQLite ``observations.db``."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.memory.observation_store import ObservationStore, observations_db_path

logger = logging.getLogger(__name__)

_OBSERVATIONS_TSV = "observations.tsv"
_MIGRATED_SUFFIX = ".migrated"
_FIELDNAMES = (
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


def observations_tsv_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / _OBSERVATIONS_TSV


def observations_tsv_migrated_path(workspace: Path) -> Path:
    return observations_tsv_path(workspace).with_suffix(
        observations_tsv_path(workspace).suffix + _MIGRATED_SUFFIX
    )


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return [dict(row) for row in csv.DictReader(f, delimiter="\t") if row]
    except OSError as exc:
        logger.warning("observations.tsv read failed: %s", exc)
        return []


def _db_row_count(store: ObservationStore) -> int:
    return int(store.stats().get("row_count") or 0)


def migrate_tsv_to_db(
    workspace: Path,
    *,
    store: ObservationStore | None = None,
    force: bool = False,
    archive_tsv: bool = True,
) -> dict[str, Any]:
    """Import legacy TSV rows into ``observations.db`` (idempotent by ``row_id``)."""
    ws = Path(workspace).expanduser().resolve()
    tsv_path = observations_tsv_path(ws)
    db_path = observations_db_path(ws)
    db = store or ObservationStore(db_path)

    if not tsv_path.is_file():
        return {
            "ok": True,
            "imported": 0,
            "reason": "no_tsv",
            "db_path": str(db_path),
            "tsv_path": str(tsv_path),
        }

    existing = _db_row_count(db)
    if existing > 0 and not force:
        return {
            "ok": True,
            "imported": 0,
            "reason": "db_nonempty",
            "existing_rows": existing,
            "db_path": str(db_path),
            "tsv_path": str(tsv_path),
        }

    rows = _read_tsv_rows(tsv_path)
    valid = [row for row in rows if str(row.get("row_id") or "").strip()]
    imported = db.insert_many(valid) if valid else 0

    archived_to = ""
    if archive_tsv and imported > 0:
        migrated_path = observations_tsv_migrated_path(ws)
        try:
            if migrated_path.is_file():
                migrated_path.unlink()
            tsv_path.rename(migrated_path)
            archived_to = str(migrated_path)
        except OSError as exc:
            logger.warning("observations.tsv archive failed: %s", exc)

    return {
        "ok": True,
        "imported": imported,
        "reason": "imported" if imported else "tsv_empty",
        "existing_rows": existing,
        "db_path": str(db_path),
        "tsv_path": str(tsv_path),
        "archived_to": archived_to,
        "migrated_at": datetime.now(timezone.utc).isoformat(),
    }


def migrate_tsv_if_needed(
    workspace: Path,
    *,
    store: ObservationStore | None = None,
) -> dict[str, Any]:
    """Auto-import when TSV exists and DB is empty (first-open path)."""
    ws = Path(workspace).expanduser().resolve()
    tsv_path = observations_tsv_path(ws)
    if not tsv_path.is_file():
        return {"ok": True, "imported": 0, "reason": "no_tsv"}
    db = store or ObservationStore(observations_db_path(ws))
    if _db_row_count(db) > 0:
        return {"ok": True, "imported": 0, "reason": "db_nonempty"}
    return migrate_tsv_to_db(ws, store=db, force=False, archive_tsv=True)


__all__ = [
    "migrate_tsv_if_needed",
    "migrate_tsv_to_db",
    "observations_tsv_migrated_path",
    "observations_tsv_path",
]
