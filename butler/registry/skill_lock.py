"""Lockfile for hub-installed skills."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.registry.paths import lock_path
from butler.registry.skill_types import InstalledSkillRecord
from butler.tools._file_cache import read_json_cached


_EMPTY_LOCK: dict[str, Any] = {"version": 1, "skills": {}}


def _row_to_record(name: str, row: dict[str, Any]) -> InstalledSkillRecord:
    return InstalledSkillRecord(
        name=str(name),
        source=str(row.get("source") or ""),
        identifier=str(row.get("identifier") or ""),
        version=row.get("version"),
        installed_at=str(row.get("installed_at") or ""),
        content_hash=str(row.get("content_hash") or ""),
        install_path=str(row.get("install_path") or ""),
        scan_verdict=str(row.get("scan_verdict") or ""),
        trust=str(row.get("trust") or "community"),
    )


class SkillLockFile:
    def __init__(self, path: Path | None = None, *, tenant_id: str = "") -> None:
        self._path = path or lock_path(tenant_id=tenant_id)

    def _load(self) -> dict[str, Any]:
        data = read_json_cached(self._path)
        if not isinstance(data, dict):
            return dict(_EMPTY_LOCK)
        data.setdefault("version", 1)
        data.setdefault("skills", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_installed(self) -> list[InstalledSkillRecord]:
        raw = self._load().get("skills") or {}
        out: list[InstalledSkillRecord] = []
        if not isinstance(raw, dict):
            return out
        for name, row in raw.items():
            if not isinstance(row, dict):
                continue
            out.append(_row_to_record(name, row))
        return sorted(out, key=lambda r: r.name)

    def get(self, name: str) -> InstalledSkillRecord | None:
        data = self._load()
        raw = data.get("skills") or {}
        if not isinstance(raw, dict):
            return None
        row = raw.get(name)
        if not isinstance(row, dict):
            return None
        return _row_to_record(name, row)

    def record_install(self, record: InstalledSkillRecord) -> None:
        data = self._load()
        skills = data.setdefault("skills", {})
        skills[record.name] = {
            "source": record.source,
            "identifier": record.identifier,
            "version": record.version,
            "installed_at": record.installed_at,
            "content_hash": record.content_hash,
            "install_path": record.install_path,
            "scan_verdict": record.scan_verdict,
            "trust": record.trust,
        }
        self._save(data)

    def remove(self, name: str) -> bool:
        data = self._load()
        skills = data.get("skills") or {}
        if name not in skills:
            return False
        del skills[name]
        self._save(data)
        return True
