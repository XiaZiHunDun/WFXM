"""Registry tools: search, propose install, and Owner-gated direct install."""

from __future__ import annotations

import json

from butler.registry.skill_service import SkillRegistryService


def register_registry_tools(register) -> None:
    register(
        name="registry_search_skills",
        description=(
            "【catalog·read-only】Query skill indexes (bundled/github/marketplace); "
            "returns identifier hits. Zero download, zero filesystem writes."
        ),
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
            "【owner-hint·text】Compose slash/WeChat install instructions for an identifier. "
            "Returns command text only; does not copy files."
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
        name="registry_install_skill",
        description=(
            "【install·mutation】Copy skill package into tenant store after Owner gate. "
            "Requires identifier; performs download/write."
        ),
        schema={
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "Skill identifier from search results"},
                "source": {"type": "string", "default": "", "description": "Source hint (github/clawhub/lobehub)"},
            },
            "required": ["identifier"],
        },
        handler=_tool_registry_install_skill,
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


def _tool_registry_install_skill(identifier: str, source: str = "", **_) -> str:
    """Install a skill — requires Owner confirmation.

    Sprint 19-1 SEC-19-A-1: 旧实现 import `butler.human_gate.is_owner_context`
    但该符号根本不存在, try/except ImportError 静默吞掉, owner gate 完全 no-op.
    改用 is_gateway_owner 真源 (Sprint 18-1 单一真源), tool 上下文从
    get_current_session_key() 解析 chat_id, 无 session_key 时 fail-closed.

    R1-10: route through ``is_current_turn_owner`` / ``owner_required_message``
    in ``butler.execution_context`` so tools → gateway stays a one-way dependency.
    """
    from butler.execution_context import (
        get_current_session_key,
        is_current_turn_owner,
        owner_required_message,
    )
    from butler.session.keys import chat_id_from_session_key

    sk = get_current_session_key() or ""
    cid = chat_id_from_session_key(sk) if sk else ""
    if not is_current_turn_owner(platform="wechat", external_id=cid, session_key=sk):
        return json.dumps({
            "error": owner_required_message(),
            "hint": f"请主人通过 /技能 安装 {identifier} 触发 (微信 owner 账号)",
        }, ensure_ascii=False)

    svc = SkillRegistryService()
    try:
        result = svc.install(identifier, confirmed=True)
        return json.dumps({
            "ok": True,
            "message": f"Skill '{identifier}' 安装完成",
            "details": str(result) if result else "",
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "error": f"安装失败: {exc}",
            "hint": "可尝试 /技能 搜索 " + identifier + " 确认标识符",
        }, ensure_ascii=False)


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
