"""Persisted usage statistics for Butler skills."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Audit R2-18: corrupt ``skill_usage.json`` is now renamed to a
# ``.corrupt-<unix_ts>`` forensic backup before the in-memory store is
# reset. The event is also recorded in a module-level diagnostics
# buffer so ``/诊断`` can surface skill-usage data loss.

_MAX_USAGE_CORRUPTION_ENTRIES = 50
_usage_data_corruption: list[dict[str, Any]] = []


def recent_usage_data_corruption() -> list[dict[str, Any]]:
    """Return recent skill-usage corruption events for ``/诊断``."""
    return list(_usage_data_corruption)


def reset_usage_data_corruption() -> None:
    """Clear the skill-usage corruption buffer (test-only)."""
    _usage_data_corruption.clear()


def _record_usage_data_corruption(path: Path, error: str, backup: str) -> None:
    """Append a corruption event to the diagnostics buffer (FIFO-capped)."""
    _usage_data_corruption.append(
        {
            "kind": "skill_usage_corrupt",
            "path": str(path),
            "error": error,
            "backup_path": backup,
            "ts": time.time(),
        }
    )
    if len(_usage_data_corruption) > _MAX_USAGE_CORRUPTION_ENTRIES:
        del _usage_data_corruption[
            : len(_usage_data_corruption) - _MAX_USAGE_CORRUPTION_ENTRIES
        ]


class UsageTracker:
    """Track create/view/use/delete/merge events per skill."""

    def __init__(self, usage_file: Path) -> None:
        self._path = Path(usage_file)
        self._data: dict[str, dict[str, Any]] = {}
        self._save_blocked: bool = False
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            return
        except (json.JSONDecodeError, OSError) as exc:
            backup_path_str, rename_ok = self._quarantine_corrupt_file(exc)
            if rename_ok:
                logger.warning(
                    "Failed to load skill usage, renamed corrupt file to %s: %s",
                    backup_path_str, exc,
                    exc_info=exc,
                )
            else:
                # Could not move the corrupt file. If we now allow _save()
                # to run, the next on_view/on_use would atomically overwrite
                # the still-corrupt original — re-creating the R2-18 data
                # loss. Block saves until an operator intervenes.
                logger.error(
                    "Failed to load skill usage AND could not rename %s: %s. "
                    "Subsequent _save() calls are blocked to prevent "
                    "overwriting the corrupt file. Inspect the file manually "
                    "and clear it before reusing this tracker.",
                    self._path, exc,
                    exc_info=exc,
                )
                self._save_blocked = True
            self._data = {}

    def _quarantine_corrupt_file(self, exc: BaseException) -> tuple[str, bool]:
        """Rename the corrupt file to ``<file>.corrupt-<ns_ts>`` for forensics.

        Returns ``(backup_path, rename_ok)``. The timestamp uses
        nanosecond resolution to avoid collisions when multiple
        corruptions of the same file occur within the same second.
        On rename failure the original file remains in place and
        ``rename_ok`` is False.
        """
        backup_name = f"{self._path.name}.corrupt-{time.time_ns()}"
        backup_path = self._path.with_name(backup_name)
        try:
            os.replace(self._path, backup_path)
            rename_ok = True
        except OSError as rename_exc:
            logger.warning(
                "Could not rename corrupt skill usage %s -> %s: %s",
                self._path, backup_path, rename_exc,
                exc_info=rename_exc,
            )
            rename_ok = False
        backup_path_str = str(backup_path)
        _record_usage_data_corruption(
            self._path, str(exc), backup_path_str,
        )
        return backup_path_str, rename_ok

    def _save(self) -> None:
        if self._save_blocked:
            # Audit R2-18 follow-up: rename failed during _load(); the
            # original corrupt file is still at self._path. Writing a
            # fresh file here would overwrite it and re-create the
            # data loss we are trying to prevent.
            logger.warning(
                "Skill usage _save() skipped: corrupt file at %s could not "
                "be quarantined; refusing to overwrite.",
                self._path,
            )
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _ensure(self, name: str) -> dict[str, Any]:
        if name not in self._data:
            self._data[name] = {
                "creates": 0,
                "views": 0,
                "uses": 0,
                "deletes": 0,
                "merges_in": 0,
                "last_event": None,
                "last_event_at": None,
            }
        return self._data[name]

    def on_create(self, name: str) -> None:
        e = self._ensure(name)
        e["creates"] = int(e.get("creates", 0)) + 1
        e["last_event"] = "create"
        e["last_event_at"] = time.time()
        self._save()

    def on_view(self, name: str) -> None:
        e = self._ensure(name)
        e["views"] = int(e.get("views", 0)) + 1
        e["last_event"] = "view"
        e["last_event_at"] = time.time()
        self._save()

    def on_use(self, name: str) -> None:
        e = self._ensure(name)
        e["uses"] = int(e.get("uses", 0)) + 1
        e["last_event"] = "use"
        e["last_event_at"] = time.time()
        self._save()

    def on_delete(self, name: str) -> None:
        """Remove persisted stats for a deleted skill."""
        self._data.pop(name, None)
        self._save()

    def on_merge(self, old_names: list[str], new_name: str) -> None:
        """Fold prior stats into *new_name* and drop merged skills."""
        merged_views = 0
        merged_uses = 0
        for old in old_names:
            if old == new_name:
                continue
            prev = self._data.pop(old, None)
            if prev:
                merged_views += int(prev.get("views", 0))
                merged_uses += int(prev.get("uses", 0))
        ne = self._ensure(new_name)
        ne["views"] = int(ne.get("views", 0)) + merged_views
        ne["uses"] = int(ne.get("uses", 0)) + merged_uses
        ne["merges_in"] = int(ne.get("merges_in", 0)) + len(
            [o for o in old_names if o and o != new_name]
        )
        ne["last_event"] = "merge"
        ne["last_event_at"] = time.time()
        self._save()

    def get_stats(self, name: str) -> dict[str, Any]:
        return dict(self._data.get(name, {}))

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        return {k: dict(v) for k, v in self._data.items()}
