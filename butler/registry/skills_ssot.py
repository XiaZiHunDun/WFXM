"""Skills SSOT index for tenant lockfile + bundled templates."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.registry.skill_lock import SkillLockFile


def skills_ssot_path(*, tenant_id: str = "default") -> Path:
    from butler.config import get_butler_home

    tid = str(tenant_id or "default").strip() or "default"
    return Path(get_butler_home()) / "tenants" / tid / "skills-ssot.yaml"


def build_skills_ssot_payload(*, tenant_id: str = "default") -> dict[str, Any]:
    lock = SkillLockFile(tenant_id=tenant_id)
    installed = lock.list_installed()
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant": tenant_id,
        "skills": [
            {
                "name": rec.name,
                "identifier": rec.identifier,
                "source": rec.source,
                "install_path": str(rec.install_path),
                "content_hash": rec.content_hash,
                "scan_verdict": rec.scan_verdict,
            }
            for rec in installed
        ],
    }


def sync_skills_ssot(*, tenant_id: str = "default", dry_run: bool = False) -> tuple[bool, str]:
    payload = build_skills_ssot_payload(tenant_id=tenant_id)
    path = skills_ssot_path(tenant_id=tenant_id)
    count = len(payload.get("skills") or [])
    if dry_run:
        return True, f"[dry-run] 将写入 {path}（{count} 条已安装技能）"
    path.parent.mkdir(parents=True, exist_ok=True)
    from butler.io.atomic_write import atomic_write_text

    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    atomic_write_text(path, text)
    return True, f"已写入 Skills SSOT: {path}（{count} 条）"


__all__ = ["build_skills_ssot_payload", "skills_ssot_path", "sync_skills_ssot"]
