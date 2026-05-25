"""TTL cache for remote registry index fetches."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.registry.paths import hub_dir

logger = logging.getLogger(__name__)

_GLOBAL_CACHE_TENANT = "__global__"


def cache_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("BUTLER_REGISTRY_CACHE_TTL", "3600")))
    except ValueError:
        return 3600


def _cache_dir(*, tenant_id: str = "") -> Path:
    if tenant_id == _GLOBAL_CACHE_TENANT:
        d = get_butler_home() / "registry-cache"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = hub_dir(tenant_id=tenant_id) / "index-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(key: str, *, tenant_id: str = "") -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return _cache_dir(tenant_id=tenant_id) / f"{digest}.json"


def read_cache(key: str, *, tenant_id: str = "") -> Any | None:
    path = _cache_path(key, tenant_id=tenant_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    ts = float(data.get("_ts") or 0)
    if time.time() - ts > cache_ttl_seconds():
        return None
    return data.get("payload")


def write_cache(key: str, payload: Any, *, tenant_id: str = "") -> None:
    path = _cache_path(key, tenant_id=tenant_id)
    try:
        path.write_text(
            json.dumps({"_ts": time.time(), "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("registry cache write failed: %s", exc)
