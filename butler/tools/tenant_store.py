"""Shared tenant-scoped JSON file store for daily-life tools.

All modules (memo, contacts, expense, habits) share the same CRUD pattern:
tenant-scoped directory with one JSON file per record. This module extracts
that pattern into a reusable base.

D7 (T7/批评4): Optional at-rest encryption via Fernet.
Set ``BUTLER_PIM_ENCRYPT=1`` + ``BUTLER_PIM_ENCRYPT_KEY=<base64-fernet-key>``
to enable transparent encrypt-on-write / decrypt-on-read.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from butler.io.atomic_write import atomic_write_text
from butler.tools._file_cache import clear_cache, read_json_cached

__all__ = ["TenantStore", "clear_cache", "read_json_cached"]

logger = logging.getLogger(__name__)


def _pim_encrypt_enabled() -> bool:
    return os.getenv("BUTLER_PIM_ENCRYPT", "0").strip() in ("1", "true", "yes")


def _get_fernet():
    """Return a Fernet instance if encryption is enabled, else None."""
    if not _pim_encrypt_enabled():
        return None
    key = os.getenv("BUTLER_PIM_ENCRYPT_KEY", "").strip()
    if not key:
        logger.warning("BUTLER_PIM_ENCRYPT=1 but BUTLER_PIM_ENCRYPT_KEY is empty; encryption disabled")
        return None
    from butler.tools.tenant_store_ops import build_fernet_safe, decrypt_fernet_payload_safe

    try:
        from cryptography.fernet import Fernet  # noqa: F401
    except ImportError:
        logger.warning("cryptography not installed; PIM encryption disabled")
        return None
    return build_fernet_safe(key)


def _encrypt_text(text: str) -> str:
    """Encrypt text if Fernet is configured; return original text otherwise."""
    f = _get_fernet()
    if f is None:
        return text
    encrypted = f.encrypt(text.encode("utf-8"))
    return "FERNET:" + base64.urlsafe_b64encode(encrypted).decode("ascii")


def _decrypt_text(text: str) -> str:
    """Decrypt text if it has the FERNET: prefix; return original otherwise."""
    if not text.startswith("FERNET:"):
        return text
    f = _get_fernet()
    if f is None:
        return text
    encrypted = base64.urlsafe_b64decode(text[7:])
    plain = decrypt_fernet_payload_safe(f, encrypted)
    return plain if plain is not None else text


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
        text = json.dumps(record, ensure_ascii=False, indent=2)
        atomic_write_text(path, _encrypt_text(text))
        return path

    def _read_and_decrypt(self, path: Path) -> dict[str, Any] | None:
        """Read a JSON file, decrypting if needed."""
        try:
            raw = path.read_text(encoding="utf-8")
            text = _decrypt_text(raw)
            data = json.loads(text)
            if isinstance(data, dict) and "id" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def load_all(self) -> list[dict[str, Any]]:
        d = self.storage_dir()
        if not d.is_dir():
            return []
        result: list[dict[str, Any]] = []
        for f in sorted(d.glob("*.json")):
            if f.name in self._skip_files:
                continue
            data = self._read_and_decrypt(f)
            if data is not None:
                result.append(data)
        return result

    def load_one(self, record_id: str) -> dict[str, Any] | None:
        path = self.storage_dir() / f"{record_id}.json"
        if not path.is_file():
            return None
        if _pim_encrypt_enabled():
            return self._read_and_decrypt(path)
        data = read_json_cached(path)
        return data if isinstance(data, dict) and data.get("id") == record_id else None

    def search(self, query: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """Substring search across record fields (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return self.load_all()

        results: list[dict[str, Any]] = []
        for record in self.load_all():
            if fields is None:
                candidates = [v for v in record.values() if isinstance(v, str)]
            else:
                candidates = []
                for key in fields:
                    val = record.get(key)
                    if isinstance(val, str):
                        candidates.append(val)
                    elif isinstance(val, list):
                        candidates.extend(item for item in val if isinstance(item, str))

            if any(q in text.lower() for text in candidates):
                results.append(record)
        return results

    def find_by_prefix(self, record_id: str) -> dict[str, Any] | None:
        """Find a record by exact ID or ID prefix match."""
        rid = record_id.strip()
        if not rid:
            return None
        exact = self.load_one(rid)
        if exact is not None:
            return exact
        for record in self.load_all():
            if record.get("id", "").startswith(rid):
                return record
        return None

    def backup(self) -> Path:
        """Create a timestamped ``.tar.gz`` snapshot of the storage directory."""
        d = self.storage_dir()
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = d.parent / "_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        archive = backup_dir / f"{self._subdir}_{ts}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(d, arcname=self._subdir)
        return archive

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
