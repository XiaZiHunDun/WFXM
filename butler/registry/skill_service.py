"""Skill registry search and install orchestration."""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, cast

from butler.registry.paths import enabled_sources, registry_enabled
from butler.registry.skill_install import (
    install_from_quarantine,
    quarantine_bundle,
    scan_quarantine,
    uninstall_skill,
)
from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_sources import (
    BundledSource,
    ClawHubSource,
    GitHubSource,
    ProjectSource,
    UrlSource,
)
from butler.registry.skill_sources.clawhub import clawhub_enabled
from butler.registry.skill_sources.lobehub import LobeHubSource, lobehub_enabled
from butler.registry.skill_sources.marketplace import (
    ClaudeMarketplaceSource,
    marketplace_enabled,
)
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_types import InstalledSkillRecord, SkillBundle, SkillSearchHit

logger = logging.getLogger(__name__)

_catalog_integrity_checked = False


def _ensure_catalog_integrity_once() -> None:
    global _catalog_integrity_checked
    if _catalog_integrity_checked:
        return
    _catalog_integrity_checked = True
    from butler.registry.skill_service_ops import ensure_catalog_integrity_safe

    ensure_catalog_integrity_safe()


def _sources() -> list[SkillSource]:
    _ensure_catalog_integrity_once()
    ids = set(enabled_sources())
    out: list[SkillSource] = []
    if "bundled" in ids:
        out.append(BundledSource())
    if "project" in ids:
        out.append(ProjectSource())
    if "github" in ids:
        out.append(GitHubSource())
    if "url" in ids:
        out.append(UrlSource())
    if "clawhub" in ids and clawhub_enabled():
        out.append(ClawHubSource())
    if "marketplace" in ids and marketplace_enabled():
        out.append(ClaudeMarketplaceSource())
    if "lobehub" in ids and lobehub_enabled():
        out.append(LobeHubSource())
    return out


_TRUST_ORDER = {"builtin": 0, "trusted": 1, "community": 2}


def _resolve_identifier(identifier: str, sources: list[SkillSource]) -> str:
    ident = identifier.strip()
    for src in sources:
        if src.inspect(ident):
            return ident
    if "/" in ident or ident.startswith("http") or ident.startswith("github:"):
        return ident
    if ident.startswith("marketplace:") or ident.startswith("claude-marketplace:"):
        return ident
    if ident.startswith("project:"):
        return ident
    if ident.startswith("lobehub:"):
        return ident
    q = ident.lower()
    exact: list[SkillSearchHit] = []
    for src in sources:
        hit = src.inspect(ident)
        if hit and hit.name.lower() == q:
            exact.append(hit)
        for row in src.search(ident, limit=10):
            if row.name.lower() == q:
                exact.append(row)
    if len(exact) == 1:
        return str(exact[0].identifier)
    if len(exact) > 1:
        raise ValueError(
            f"Ambiguous skill name '{ident}'. Use full identifier: "
            + ", ".join(h.identifier for h in exact[:3])
        )
    raise ValueError(f"No skill named '{ident}' found.")


class SkillRegistryService:
    def __init__(self, *, tenant_id: str = "") -> None:
        self.tenant_id = tenant_id

    def search(
        self,
        query: str,
        *,
        source_filter: str = "all",
        limit: int = 20,
    ) -> list[SkillSearchHit]:
        if not registry_enabled():
            return []
        hits: list[SkillSearchHit] = []
        from butler.registry.skill_service_ops import search_source_safe

        for src in _sources():
            if source_filter != "all" and src.source_id != source_filter:
                continue
            hits.extend(search_source_safe(src, query, limit=limit))
        seen: set[str] = set()
        out: list[SkillSearchHit] = []
        for h in sorted(
            hits,
            key=lambda x: (_TRUST_ORDER.get(x.trust, 9), x.name.lower()),
        ):
            if h.identifier in seen:
                continue
            seen.add(h.identifier)
            out.append(h)
            if len(out) >= limit:
                break
        return out

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        from butler.registry.skill_service_ops import inspect_source_safe

        for src in _sources():
            hit = inspect_source_safe(src, identifier)
            if hit:
                return hit
        return None

    def fetch_bundle(self, identifier: str) -> SkillBundle:
        sources = _sources()
        ident = _resolve_identifier(identifier, sources)
        from butler.registry.skill_service_ops import fetch_from_source_safe

        for src in sources:
            bundle = fetch_from_source_safe(src, ident)
            if bundle:
                return bundle
        raise ValueError(f"Could not fetch skill '{ident}' from any source.")

    def needs_install_confirmation(self, *, trust: str, force: bool = False, confirmed: bool = False) -> bool:
        if force or confirmed:
            return False
        if trust in ("builtin", "trusted"):
            return False
        # Sprint 19-3 SEC-19-3: prod 环境硬拒 BUTLER_REGISTRY_AUTO_INSTALL 越权 BYPASS.
        # 防 .env 误带上线 / CI 残留 → community skill 无确认自动 install. 模式同
        # Sprint 18-2 (BUTLER_PROJECT_CREATE_OPEN prod 禁用).
        from butler.env_parse import is_butler_prod

        if is_butler_prod():
            return True
        allow = os.getenv("BUTLER_REGISTRY_AUTO_INSTALL", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        return not allow

    def install(
        self,
        identifier: str,
        *,
        name_override: str = "",
        force: bool = False,
        confirmed: bool = False,
    ) -> InstalledSkillRecord:
        hit = self.inspect(identifier)
        bundle = self.fetch_bundle(identifier)
        if name_override:
            bundle.name = name_override.strip().lower()

        lock = SkillLockFile(tenant_id=self.tenant_id)
        existing = lock.get(bundle.name)
        if existing and not force:
            raise ValueError(
                f"Skill '{bundle.name}' already installed. Use --force to replace."
            )

        trust = bundle.trust or (hit.trust if hit else "community")
        if self.needs_install_confirmation(trust=trust, force=force, confirmed=confirmed):
            from butler.registry.registry_errors import InstallConfirmationRequired

            if hit is None:
                hit = SkillSearchHit(
                    name=bundle.name,
                    description="",
                    source=bundle.source,
                    identifier=bundle.identifier,
                    trust=trust,
                )
            raise InstallConfirmationRequired(hit)

        from butler.registry.skill_service_ops import run_pre_install_scan_safe

        run_pre_install_scan_safe(bundle, hit)

        qpath = quarantine_bundle(bundle, tenant_id=self.tenant_id)
        verdict, issues = scan_quarantine(qpath)
        if verdict == "block":
            shutil.rmtree(qpath, ignore_errors=True)
            raise ValueError(f"Install blocked: {', '.join(issues)}")

        return install_from_quarantine(
            qpath,
            bundle,
            tenant_id=self.tenant_id,
            name_override=name_override,
        )

    def upgrade(
        self,
        identifier: str = "",
        *,
        name: str = "",
        force: bool = True,
    ) -> InstalledSkillRecord:
        """Re-fetch and reinstall a hub-managed skill (by lock name or identifier)."""
        lock = SkillLockFile(tenant_id=self.tenant_id)
        rec = None
        if name.strip():
            rec = lock.get(name.strip())
        elif identifier.strip():
            ident = identifier.strip()
            for row in lock.list_installed():
                if row.identifier == ident or row.name == ident:
                    rec = row
                    break
        if rec is None:
            raise ValueError("未找到已安装的 registry 技能（请提供名称或 identifier）")
        return self.install(rec.identifier, force=force)

    def uninstall(self, name: str) -> tuple[bool, str]:
        return cast(tuple[bool, str], uninstall_skill(name, tenant_id=self.tenant_id))

    def list_installed(self) -> list[InstalledSkillRecord]:
        return list(SkillLockFile(tenant_id=self.tenant_id).list_installed())

    def format_search_table(self, hits: list[SkillSearchHit]) -> str:
        if not hits:
            return "无匹配技能。"
        lines = ["技能搜索结果:", ""]
        for h in hits:
            lines.append(
                f"• [{h.source}/{h.trust}] {h.name}\n"
                f"  id: {h.identifier}\n"
                f"  {h.description[:160]}"
            )
        lines.append(
            "\n安装: butler skills install <identifier>"
            "\n升级: butler skills upgrade <name>"
            "\n微信: /技能 安装 <id> → /确认安装 <id>（community 源）"
        )
        return "\n".join(lines)

    def propose_install_command(self, identifier: str) -> str:
        return (
            f"请 Owner 执行安装:\n"
            f"  CLI: butler skills install {identifier}\n"
            f"  微信: /技能 安装 {identifier}"
        )

    def install_followup(
        self,
        identifier: str,
        *,
        record: InstalledSkillRecord | None = None,
    ) -> str:
        from butler.registry.marketplace_compat import format_install_followup
        from butler.registry.skills_project_sync import maybe_sync_after_registry_install

        parts: list[str] = []
        compat = format_install_followup(identifier)
        if compat:
            parts.append(compat)
        if record is not None:
            sync_msg = maybe_sync_after_registry_install(record, tenant_id=self.tenant_id)
            if sync_msg:
                parts.append(sync_msg)
        return "\n".join(parts)
