"""Best-effort probes for registry / 诊断 lines (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.ops.rag_diagnostics_ops import append_probe_line


def append_registry_enabled_line(lines: list[str]) -> None:
    def _build() -> str:
        from butler.registry.paths import registry_enabled

        return (
            f"Skill Registry: {'开' if registry_enabled() else '关'} "
            "(BUTLER_SKILL_REGISTRY)"
        )

    append_probe_line(lines, label="registry_diagnostics.enabled", build=_build)


def append_marketplace_index_line(lines: list[str]) -> None:
    def _run() -> None:
        from butler.registry.skill_sources.marketplace import (
            ClaudeMarketplaceSource,
            marketplace_enabled,
        )

        if not marketplace_enabled():
            return
        mp_hits = ClaudeMarketplaceSource().search("", limit=50)
        if mp_hits:
            lines.append(f"Marketplace 索引: {len(mp_hits)} 个插件")

    safe_best_effort(_run, label="registry_diagnostics.marketplace", default=None)


def append_installed_skills_lines(lines: list[str]) -> None:
    def _run() -> None:
        from butler.config import load_settings
        from butler.registry.skill_service import SkillRegistryService

        tenant = load_settings().default_tenant
        n = len(SkillRegistryService(tenant_id=tenant).list_installed())
        if n:
            lines.append(f"已安装技能 (registry): {n}")
        append_marketplace_index_line(lines)

    safe_best_effort(_run, label="registry_diagnostics.installed_skills", default=None)


def append_mcp_catalog_line(lines: list[str]) -> None:
    def _build() -> str:
        from butler.registry.mcp_catalog import McpCatalogService, mcp_catalog_enabled

        if not mcp_catalog_enabled():
            return ""
        svc = McpCatalogService()
        cat_n = len(svc._load_entries())
        inst = svc.list_installed_ids()
        remote_n = max(0, cat_n - len(svc._load_bundled_entries()))
        return (
            f"MCP 目录: {cat_n} 模板"
            + (f" (远程 +{remote_n})" if remote_n else "")
            + f", 全局 yaml {len(inst)} 个"
        )

    append_probe_line(lines, label="registry_diagnostics.mcp_catalog", build=_build)


def extend_mcp_merge_lines(lines: list[str], *, session_key: str) -> None:
    def _run() -> None:
        from butler.registry.mcp_merge import (
            format_mcp_merge_diagnostic_lines,
            resolve_workspace_for_session,
        )

        ws = resolve_workspace_for_session(session_key)
        merge_lines = format_mcp_merge_diagnostic_lines(workspace=ws)
        if merge_lines:
            lines.extend(merge_lines[:6])

    safe_best_effort(_run, label="registry_diagnostics.mcp_merge", default=None)


def append_mcp_lock_error_lines(lines: list[str]) -> None:
    def _run() -> None:
        import json

        from butler.registry.paths import mcp_lock_path

        path = mcp_lock_path()
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        servers = data.get("servers") if isinstance(data, dict) else {}
        if not isinstance(servers, dict) or not servers:
            return
        for sid, row in list(servers.items())[:3]:
            probe = (row or {}).get("probe") if isinstance(row, dict) else {}
            err = (probe or {}).get("error") if isinstance(probe, dict) else ""
            if err:
                lines.append(f"MCP lock {sid}: {str(err)[:80]}")

    safe_best_effort(_run, label="registry_diagnostics.mcp_lock", default=None)
