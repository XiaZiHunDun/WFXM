"""WeChat slash commands for skill/MCP registry."""

from __future__ import annotations

import time

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def handle_confirm_install_command(
    arg: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    """Handle /确认安装 <identifier> (Owner)."""
    gate = _require_owner(platform, external_id, session_key)
    if gate:
        return gate
    ident = (arg or "").strip()
    if not ident:
        return "用法: /确认安装 <identifier>\n例: /确认安装 clawhub:demo-skill"
    return _confirm_skill_install(
        ident,
        platform=platform,
        external_id=external_id,
        session_key=session_key,
    )


def _confirm_skill_install(
    identifier: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    from butler.registry.install_pending import clear_pending, get_pending
    from butler.registry.skill_service import SkillRegistryService

    svc = SkillRegistryService(tenant_id=_tenant_id())
    pending = get_pending(
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        identifier=identifier,
    )
    ident = (pending.identifier if pending else identifier).strip()
    try:
        rec = svc.install(ident, confirmed=True, force=True)
    except ValueError as exc:
        return f"安装失败: {exc}"
    clear_pending(
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        identifier=ident,
    )
    return f"已确认并安装技能 {rec.name}（{rec.install_path}，{rec.scan_verdict}）"


def handle_registry_command(
    cmd: str,
    arg: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str | None:
    """Handle /技能 and /mcp commands."""
    if cmd in ("/技能", "/skills"):
        return _handle_skills(arg, platform=platform, external_id=external_id, session_key=session_key)
    if cmd in ("/mcp",):
        return _handle_mcp(arg, platform=platform, external_id=external_id, session_key=session_key)
    return None


def _require_owner(platform: str, external_id: str | None, session_key: str) -> str | None:
    if not is_gateway_owner(platform=platform, external_id=external_id, session_key=session_key):
        return owner_required_message()
    return None


def _tenant_id() -> str:
    try:
        from butler.config import load_settings

        return load_settings().default_tenant
    except Exception:
        return "default"


def _handle_skills(
    arg: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    # Sprint 11 SEC-11-4: read-only 子命令（搜索/列表/查看）也守门，
    # 避免第三方恶意 Skill 描述喂回 LLM 形成 prompt injection
    gate = _require_owner(platform, external_id, session_key)
    if gate:
        return gate
    from butler.registry.skill_service import SkillRegistryService

    parts = (arg or "").strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "搜索"
    rest = parts[1].strip() if len(parts) > 1 else ""

    svc = SkillRegistryService(tenant_id=_tenant_id())

    if sub in ("搜索", "search", ""):
        q = rest or "lingwen"
        return svc.format_search_table(svc.search(q))

    if sub in ("列表", "list", "已安装"):
        rows = svc.list_installed()
        if not rows:
            return "已安装技能: (无 registry 记录)"
        lines = ["已安装技能 (registry):"]
        for r in rows:
            lines.append(f"  • {r.name} ← {r.identifier} [{r.scan_verdict}]")
        return "\n".join(lines)

    if sub in ("查看", "inspect", "详情"):
        if not rest:
            return "用法: /技能 查看 <identifier>"
        hit = svc.inspect(rest)
        if not hit:
            return f"未找到技能: {rest}"
        extra = ""
        if hit.source in ("clawhub", "lobehub") or hit.trust == "community":
            extra = "\n⚠ community 源需 Owner 确认：/技能 安装 后回复 /确认安装 <id>"
        return (
            f"{hit.name} [{hit.source}/{hit.trust}]\n"
            f"id: {hit.identifier}\n"
            f"{hit.description[:300]}{extra}"
        )

    if sub in ("确认", "confirm"):
        if not rest:
            return "用法: /技能 确认 <identifier>"
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        return _confirm_skill_install(
            rest,
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )

    if sub in ("取消安装", "cancel-install", "取消"):
        if rest and rest not in ("安装", "install"):
            return "用法: /技能 取消安装"
        from butler.registry.install_pending import clear_pending, get_pending

        pending = get_pending(
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )
        if not pending:
            return "当前无待确认的技能安装。"
        clear_pending(
            session_key=session_key,
            platform=platform,
            external_id=external_id,
            identifier=pending.identifier,
        )
        return f"已取消待安装: {pending.identifier}"

    if sub in ("强制安装", "force-install"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /技能 强制安装 <identifier>"
        try:
            rec = svc.install(rest, force=True, confirmed=True)
        except ValueError as exc:
            return f"安装失败: {exc}"
        return f"已安装技能 {rec.name}（{rec.install_path}，{rec.scan_verdict}）"

    if sub in ("安装", "install"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /技能 安装 <identifier>\n例: /技能 安装 bundled:lingwen-project-lead"
        try:
            rec = svc.install(rest)
        except Exception as exc:
            from butler.registry.registry_errors import InstallConfirmationRequired

            if isinstance(exc, InstallConfirmationRequired):
                h = exc.hit
                from butler.registry.install_pending import (
                    PendingSkillInstall,
                    format_pending_prompt,
                    save_pending,
                )

                save_pending(
                    PendingSkillInstall(
                        identifier=h.identifier,
                        name=h.name,
                        description=h.description,
                        source=h.source,
                        trust=h.trust,
                        session_key=session_key,
                        platform=platform,
                        external_id=external_id or "",
                        requested_at=time.time(),
                    )
                )
                return format_pending_prompt(h.name, h.identifier, h.source, h.trust)
            if isinstance(exc, ValueError):
                return f"安装失败: {exc}"
            raise
        warn = "（community 源）" if rec.trust == "community" else ""
        return f"已安装技能 {rec.name}（{rec.install_path}，{rec.scan_verdict}）{warn}"

    if sub in ("升级", "upgrade"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /技能 升级 <名称或 identifier>"
        try:
            if "/" in rest or rest.startswith("clawhub:"):
                rec = svc.upgrade(identifier=rest)
            else:
                rec = svc.upgrade(name=rest)
        except ValueError as exc:
            return f"升级失败: {exc}"
        return f"已升级技能 {rec.name}（hash={rec.content_hash}）"

    if sub in ("卸载", "uninstall"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /技能 卸载 <name>"
        ok, msg = svc.uninstall(rest)
        return msg

    return (
        "技能目录命令:\n"
        "  /技能 搜索 [关键词]\n"
        "  /技能 列表\n"
        "  /技能 查看 <id>\n"
        "  /技能 安装 <id>（community 需再 /确认安装）\n"
        "  /技能 确认 <id> | /确认安装 <id>\n"
        "  /技能 强制安装 <id>\n"
        "  /技能 升级 <name>（仅 Owner）\n"
        "  /技能 卸载 <name>（仅 Owner）"
    )


def _handle_mcp(
    arg: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    from butler.registry.mcp_catalog import McpCatalogService
    from butler.registry.mcp_install import (
        install_catalog_server,
        probe_server,
        reload_mcp_connections,
        remove_mcp_server,
    )
    from butler.registry.mcp_merge import format_mcp_status_message, resolve_workspace_for_session

    parts = (arg or "").strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else "列表"
    rest = parts[1].strip() if len(parts) > 1 else ""

    svc = McpCatalogService()

    if sub in ("搜索", "search"):
        return svc.format_search(svc.search(rest))

    if sub in ("列表", "list", "状态", "status", ""):
        ws = resolve_workspace_for_session(session_key)
        return format_mcp_status_message(workspace=ws, include_catalog=True)

    if sub in ("查看", "inspect", "详情"):
        if not rest:
            return "用法: /mcp 查看 <id>"
        entry = svc.get(rest)
        if entry is None:
            return f"未找到 MCP 目录项: {rest}"
        return svc.format_inspect(entry)

    if sub in ("安装", "add"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /mcp 安装 <id>\n例: /mcp 安装 github"
        ws = resolve_workspace_for_session(session_key)
        use_project = ws is not None
        ok, msg = install_catalog_server(
            rest,
            workspace=ws,
            use_project=use_project,
        )
        return msg if ok else f"失败: {msg}"

    if sub in ("移除", "remove", "卸载"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /mcp 移除 <id>"
        ws = resolve_workspace_for_session(session_key)
        ok, msg = remove_mcp_server(rest, workspace=ws)
        return msg if ok else f"失败: {msg}"

    if sub in ("测试", "test"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        if not rest:
            return "用法: /mcp 测试 <server_id>"
        import yaml

        from butler.registry.paths import default_mcp_config_path

        path = default_mcp_config_path()
        if not path.is_file():
            return "mcp.yaml 不存在"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        block = (data.get("servers") or {}).get(rest)
        if not block:
            return f"未在 mcp.yaml 中找到: {rest}"
        probe = probe_server(rest, block)
        return f"探测 {rest}: ok={probe.get('ok')} tools={probe.get('tool_count')} {probe.get('error', '')}"

    if sub in ("重载", "reload"):
        gate = _require_owner(platform, external_id, session_key)
        if gate:
            return gate
        ok, msg = reload_mcp_connections()
        return msg if ok else f"失败: {msg}"

    return (
        "MCP 目录命令:\n"
        "  /mcp 列表|状态 — 合并视图（项目 .butler + 全局）\n"
        "  /mcp 搜索 <词>\n"
        "  /mcp 查看 <id>\n"
        "  /mcp 安装 <id>（仅 Owner；有项目则写入 .butler/mcp.yaml）\n"
        "  /mcp 移除 <id>\n"
        "  /mcp 测试 <id>（仅 Owner）\n"
        "  /mcp 重载"
    )
