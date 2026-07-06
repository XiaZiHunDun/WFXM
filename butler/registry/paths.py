"""Registry filesystem paths."""

from __future__ import annotations

import os
from pathlib import Path

from butler.config import get_butler_home
from butler.tenant import normalize_tenant_id, tenant_skills_dir


def registry_enabled() -> bool:
    raw = os.getenv("BUTLER_SKILL_REGISTRY", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def enabled_sources() -> list[str]:
    raw = os.getenv(
        "BUTLER_SKILL_REGISTRY_SOURCES",
        "bundled,project,github,url,clawhub,marketplace,lobehub",
    ).strip()
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def resolve_tenant_id(tenant_id: str = "") -> str:
    if tenant_id.strip():
        return str(normalize_tenant_id(tenant_id))
    from butler.registry.registry_paths_ops import resolve_tenant_id_safe

    return str(resolve_tenant_id_safe())


def skills_root(*, tenant_id: str = "") -> Path:
    return Path(tenant_skills_dir(Path(get_butler_home()), resolve_tenant_id(tenant_id)))


def hub_dir(*, tenant_id: str = "") -> Path:
    return Path(skills_root(tenant_id=tenant_id)) / ".hub"


def quarantine_dir(*, tenant_id: str = "") -> Path:
    return Path(hub_dir(tenant_id=tenant_id)) / "quarantine"


def lock_path(*, tenant_id: str = "") -> Path:
    return Path(hub_dir(tenant_id=tenant_id)) / "lock.json"


def audit_path() -> Path:
    return Path(get_butler_home()) / "audit" / "registry.log"


def mcp_lock_path() -> Path:
    return Path(get_butler_home()) / "mcp.lock.json"


def catalog_dir() -> Path:
    return Path(__file__).resolve().parent / "catalog"


def default_mcp_config_path() -> Path:
    env = os.getenv("BUTLER_MCP_CONFIG", "").strip()
    if env:
        return Path(env).expanduser()
    return Path(get_butler_home()) / "mcp.yaml"
