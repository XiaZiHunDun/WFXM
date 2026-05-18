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


class UsageTracker:
    """Track create/view/use/delete/merge events per skill."""

    def __init__(self, usage_file: Path) -> None:
        self._path = Path(usage_file)
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load skill usage: %s", e)
                self._data = {}

    def _save(self) -> None:
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
