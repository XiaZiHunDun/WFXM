"""Registry tools: search-only + propose install (no direct install)."""

from __future__ import annotations

import json

from butler.registry.skill_service import SkillRegistryService


def register_registry_tools(register) -> None:
    register(
        name="registry_search_skills",
        description="Search skill catalogs (read-only). Returns identifiers for Owner install.",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or URL"},
                "source": {
                    "type": "string",
                    "description": "all | bundled | project | github | url | clawhub | marketplace | lobehub",
                    "default": "all",
                },
            },
            "required": ["query"],
        },
        handler=_tool_registry_search_skills,
        toolset="registry",
    )

    register(
        name="registry_propose_skill_install",
        description=(
            "Return Owner-only install command for a skill identifier. "
            "Does not install."
        ),
        schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Skill identifier"},
            },
            "required": ["identifier"],
        },
        handler=_tool_registry_propose_skill_install,
        toolset="registry",
    )

    register(
        name="registry_search_mcp",
        description="Search curated MCP server catalog (read-only). Owner installs via butler mcp add or /mcp 安装.",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
            },
        },
        handler=_tool_registry_search_mcp,
        toolset="registry",
    )


def _tool_registry_search_skills(query: str, source: str = "all", **_) -> str:
    try:
        from butler.config import load_settings

        tenant = load_settings().default_tenant
    except Exception:
        tenant = "default"
    svc = SkillRegistryService(tenant_id=tenant)
    hits = svc.search(query, source_filter=source or "all")
    payload = [
        {
            "name": h.name,
            "identifier": h.identifier,
            "source": h.source,
            "trust": h.trust,
            "description": h.description[:300],
        }
        for h in hits
    ]
    return json.dumps({"skills": payload}, ensure_ascii=False)


def _tool_registry_propose_skill_install(identifier: str, **_) -> str:
    svc = SkillRegistryService()
    return json.dumps(
        {
            "action": "propose_only",
            "message": svc.propose_install_command(identifier),
        },
        ensure_ascii=False,
    )


def _tool_registry_search_mcp(query: str = "", **_) -> str:
    from butler.registry.mcp_catalog import McpCatalogService

    svc = McpCatalogService()
    entries = svc.search(query or "")
    payload = [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description[:200],
            "transport": e.transport,
        }
        for e in entries
    ]
    return json.dumps({"mcp_catalog": payload}, ensure_ascii=False)
