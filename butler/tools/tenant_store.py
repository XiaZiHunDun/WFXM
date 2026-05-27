"""Shared tenant-scoped JSON file store for daily-life tools.

All modules (memo, contacts, expense, habits) share the same CRUD pattern:
tenant-scoped directory with one JSON file per record. This module extracts
that pattern into a reusable base.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TenantStore:
    """Tenant-scoped JSON record store.

    Each record is stored as ``<dir>/<id>.json``.
    """

    def __init__(self, subdir: str, *, env_toggle: str = "", skip_files: frozenset[str] | None = None):
        self._subdir = subdir
        self._env_toggle = env_toggle
        self._skip_files = skip_files or frozenset()

    def enabled(self) -> bool:
        if not self._env_toggle:
            return True
        return os.getenv(self._env_toggle, "1").strip() not in ("0", "false", "no")

    def storage_dir(self) -> Path:
        from butler.config import get_butler_home
        from butler.tenant import DEFAULT_TENANT, tenant_root

        tenant_id = os.getenv("BUTLER_TENANT", DEFAULT_TENANT)
        root = tenant_root(get_butler_home(), tenant_id)
        return root / self._subdir

    def save(self, record: dict[str, Any]) -> Path:
        d = self.storage_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{record['id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_all(self) -> list[dict[str, Any]]:
        d = self.storage_dir()
        if not d.is_dir():
            return []
        result: list[dict[str, Any]] = []
        for f in sorted(d.glob("*.json")):
            if f.name in self._skip_files:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "id" in data:
                    result.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def load_one(self, record_id: str) -> dict[str, Any] | None:
        path = self.storage_dir() / f"{record_id}.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and data.get("id") == record_id else None
        except (json.JSONDecodeError, OSError):
            return None

    def delete(self, record_id: str) -> bool:
        path = self.storage_dir() / f"{record_id}.json"
        if path.is_file():
            path.unlink()
            return True
        return False

    def count(self, *, predicate: Any = None) -> int:
        """Count records, optionally filtered by a predicate function."""
        records = self.load_all()
        if predicate is None:
            return len(records)
        return sum(1 for r in records if predicate(r))
