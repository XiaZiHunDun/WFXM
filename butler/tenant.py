"""Tenant (company) scoping for Butler global memory and skills."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.config import ButlerSettings
    from butler.project import Project

logger = logging.getLogger(__name__)

DEFAULT_TENANT = "default"
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def normalize_tenant_id(raw: str) -> str:
    """Return a filesystem-safe tenant slug."""
    key = str(raw or "").strip().lower()
    if not key:
        return DEFAULT_TENANT
    key = re.sub(r"[^a-z0-9._-]+", "-", key)
    key = key.strip("-._") or DEFAULT_TENANT
    if not _TENANT_RE.match(key):
        key = DEFAULT_TENANT
    return key


def tenant_root(butler_home: Path, tenant_id: str) -> Path:
    return Path(butler_home).expanduser().resolve() / "tenants" / normalize_tenant_id(tenant_id)


def tenant_memory_dir(butler_home: Path, tenant_id: str) -> Path:
    return tenant_root(butler_home, tenant_id) / "memory"


def tenant_skills_dir(butler_home: Path, tenant_id: str) -> Path:
    return tenant_root(butler_home, tenant_id) / "skills"


def resolve_tenant_for_project(
    project: "Project | None",
    settings: "ButlerSettings | None" = None,
) -> str:
    """Tenant for the active project, else Butler ``default_tenant``, else ``default``."""
    if project is not None and str(getattr(project, "tenant", "") or "").strip():
        return normalize_tenant_id(project.tenant)
    if settings is not None and str(getattr(settings, "default_tenant", "") or "").strip():
        return normalize_tenant_id(settings.default_tenant)
    return DEFAULT_TENANT


def migrate_legacy_memory_layout(butler_home: Path) -> None:
    """Move pre-tenant ``~/.butler/memory`` and ``skills`` into ``tenants/default/``."""
    home = Path(butler_home).expanduser().resolve()
    legacy_mem = home / "memory"
    legacy_skills = home / "skills"
    target_mem = tenant_memory_dir(home, DEFAULT_TENANT)
    target_skills = tenant_skills_dir(home, DEFAULT_TENANT)

    if legacy_mem.exists() and not target_mem.exists():
        target_mem.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_mem), str(target_mem))
        logger.info("Migrated Butler memory to %s", target_mem)

    if legacy_skills.exists() and not target_skills.exists():
        target_skills.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_skills), str(target_skills))
        logger.info("Migrated Butler skills to %s", target_skills)

    from butler.tools.reminder import migrate_legacy_reminders

    migrate_legacy_reminders(home)


__all__ = [
    "DEFAULT_TENANT",
    "migrate_legacy_memory_layout",
    "normalize_tenant_id",
    "resolve_tenant_for_project",
    "tenant_memory_dir",
    "tenant_root",
    "tenant_skills_dir",
]
