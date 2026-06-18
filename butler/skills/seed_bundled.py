"""Copy repo skill templates into tenant-global skills dir (idempotent)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLED: tuple[tuple[str, str], ...] = (
    ("design-system", "docs/templates/skills/design-system.md"),
    ("research-program", "docs/templates/skills/research-program.md"),
    ("deep-research", "docs/templates/skills/deep-research.md"),
)


def ensure_bundled_tenant_skills(butler_home: Path, tenant_id: str = "default") -> list[Path]:
    """Install or refresh bundled skills under ``tenants/<id>/skills/``."""
    from butler.tenant import normalize_tenant_id, tenant_skills_dir

    home = Path(butler_home).expanduser().resolve()
    tid = normalize_tenant_id(tenant_id)
    skills_dir = tenant_skills_dir(home, tid)
    skills_dir.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    for name, rel in _BUNDLED:
        src = (_REPO_ROOT / rel).resolve()
        dest = skills_dir / f"{name}.md"
        if not src.is_file():
            continue
        try:
            if dest.is_file() and dest.read_bytes() == src.read_bytes():
                continue
            shutil.copy2(src, dest)
            installed.append(dest)
            logger.info("Synced bundled skill %s -> %s", name, dest)
        except OSError as exc:
            logger.warning("Bundled skill install failed %s: %s", name, exc)
    return installed


__all__ = ["ensure_bundled_tenant_skills"]
