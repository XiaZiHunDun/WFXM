"""Registry diagnostics for /诊断."""

from __future__ import annotations

from typing import Any
import logging


logger = logging.getLogger(__name__)

def format_registry_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    lines: list[str] = []
    try:
        from butler.registry.paths import registry_enabled

        lines.append(
            f"Skill Registry: {'开' if registry_enabled() else '关'} (BUTLER_SKILL_REGISTRY)"
        )
    except Exception as exc:
        logger.debug("format registry diagnostic lines skipped: %s", exc)
    try:
        from butler.registry.skill_service import SkillRegistryService
        from butler.config import load_settings

        tenant = load_settings().default_tenant
        n = len(SkillRegistryService(tenant_id=tenant).list_installed())
        if n:
            lines.append(f"已安装技能 (registry): {n}")
        try:
            from butler.registry.skill_sources.marketplace import marketplace_enabled

            if marketplace_enabled():
                from butler.registry.skill_sources.marketplace import ClaudeMarketplaceSource

                mp_hits = ClaudeMarketplaceSource().search("", limit=50)
                if mp_hits:
                    lines.append(f"Marketplace 索引: {len(mp_hits)} 个插件")
        except Exception as exc:
            logger.debug("format registry diagnostic lines skipped: %s", exc)
    except Exception as exc:
        logger.debug("format registry diagnostic lines skipped: %s", exc)
    try:
        from butler.registry.mcp_catalog import mcp_catalog_enabled, McpCatalogService

        if mcp_catalog_enabled():
            svc = McpCatalogService()
            cat_n = len(svc._load_entries())
            inst = svc.list_installed_ids()
            remote_n = max(0, cat_n - len(svc._load_bundled_entries()))
            lines.append(
                f"MCP 目录: {cat_n} 模板"
                + (f" (远程 +{remote_n})" if remote_n else "")
                + f", 全局 yaml {len(inst)} 个"
            )
    except Exception as exc:
        logger.debug("format registry diagnostic lines skipped: %s", exc)
    try:
        from butler.registry.mcp_merge import (
            format_mcp_merge_diagnostic_lines,
            resolve_workspace_for_session,
        )

        ws = resolve_workspace_for_session(session_key)
        merge_lines = format_mcp_merge_diagnostic_lines(workspace=ws)
        if merge_lines:
            lines.extend(merge_lines[:6])
    except Exception as exc:
        logger.debug("format registry diagnostic lines skipped: %s", exc)
    try:
        from butler.registry.paths import mcp_lock_path
        import json

        path = mcp_lock_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            servers = data.get("servers") if isinstance(data, dict) else {}
            if isinstance(servers, dict) and servers:
                for sid, row in list(servers.items())[:3]:
                    probe = (row or {}).get("probe") if isinstance(row, dict) else {}
                    err = (probe or {}).get("error") if isinstance(probe, dict) else ""
                    if err:
                        lines.append(f"MCP lock {sid}: {str(err)[:80]}")
    except Exception as exc:
        logger.debug("format registry diagnostic lines skipped: %s", exc)
    return lines
