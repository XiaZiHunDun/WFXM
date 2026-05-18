"""UsageTracker — lightweight skill usage tracking via .usage.json.

Tracks views, uses, creation time, and source for each skill.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class UsageTracker:
    """Track skill usage statistics in a JSON file."""

    def __init__(self, usage_file: Path):
        self._path = usage_file
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load usage data: %s", e)
                self._data = {}

    def _save(self):
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

    def _ensure_entry(self, name: str) -> Dict[str, Any]:
        if name not in self._data:
            self._data[name] = {
                "views": 0,
                "uses": 0,
                "created_at": None,
                "last_used_at": None,
                "last_viewed_at": None,
                "source": "manual",
            }
        return self._data[name]

    def on_view(self, name: str) -> None:
        entry = self._ensure_entry(name)
        entry["views"] = entry.get("views", 0) + 1
        entry["last_viewed_at"] = time.time()
        self._save()

    def on_use(self, name: str) -> None:
        entry = self._ensure_entry(name)
        entry["uses"] = entry.get("uses", 0) + 1
        entry["last_used_at"] = time.time()
        self._save()

    def on_create(self, name: str, source: str = "manual") -> None:
        entry = self._ensure_entry(name)
        entry["created_at"] = time.time()
        entry["source"] = source
        self._save()

    def on_delete(self, name: str) -> None:
        self._data.pop(name, None)
        self._save()

    def on_merge(self, new_name: str, old_names: list[str], source: str = "merged") -> None:
        """Record a merge: create entry for new, remove old entries."""
        total_views = 0
        total_uses = 0
        for old in old_names:
            old_entry = self._data.get(old, {})
            total_views += old_entry.get("views", 0)
            total_uses += old_entry.get("uses", 0)
            self._data.pop(old, None)

        entry = self._ensure_entry(new_name)
        entry["views"] = entry.get("views", 0) + total_views
        entry["uses"] = entry.get("uses", 0) + total_uses
        entry["created_at"] = time.time()
        entry["source"] = source
        self._save()

    def get_stats(self, name: str) -> Optional[Dict[str, Any]]:
        return self._data.get(name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._data)

    def reload(self) -> None:
        self._load()
