"""CLI extensions for butler mcp catalog subcommands."""

from __future__ import annotations

import argparse

from butler.registry.mcp_catalog import McpCatalogService
from butler.registry.mcp_install import (
    install_catalog_server,
    probe_server,
    reload_mcp_connections,
    remove_mcp_server,
)
from butler.registry.mcp_merge import format_mcp_status_message, resolve_workspace_for_session


def register_mcp_catalog_parsers(mcp_sub: argparse._SubParsersAction) -> None:
    p_search = mcp_sub.add_parser("search", help="搜索 MCP 目录")
    p_search.add_argument("query", nargs="?", default="")
    p_search.set_defaults(func=_cmd_mcp_search)

    p_add = mcp_sub.add_parser("add", help="从目录安装到 mcp.yaml")
    p_add.add_argument("server_id")
    p_add.add_argument("--env", action="append", default=[], help="KEY=VALUE")
    p_add.add_argument(
        "--workspace",
        default="",
        help="写入项目 <workspace>/.butler/mcp.yaml（需与 --project 或单独指定）",
    )
    p_add.add_argument(
        "--project",
        action="store_true",
        help="写入当前会话绑定项目的 .butler/mcp.yaml（无绑定时需 --workspace）",
    )
    p_add.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="强制写入全局 ~/.butler/mcp.yaml",
    )
    p_add.set_defaults(func=_cmd_mcp_add)

    p_rm = mcp_sub.add_parser("remove", help="从 mcp.yaml 移除")
    p_rm.add_argument("server_id")
    p_rm.add_argument("--workspace", default="")
    p_rm.set_defaults(func=_cmd_mcp_remove)

    p_list = mcp_sub.add_parser("list", help="目录 + 已配置")
    p_list.set_defaults(func=_cmd_mcp_list)

    p_status = mcp_sub.add_parser("status", help="项目 + 全局 mcp.yaml 合并视图")
    p_status.add_argument(
        "--workspace",
        default="",
        help="项目工作区路径（默认从当前会话项目解析）",
    )
    p_status.set_defaults(func=_cmd_mcp_status)

    p_inspect = mcp_sub.add_parser("inspect", help="查看目录模板详情")
    p_inspect.add_argument("server_id")
    p_inspect.set_defaults(func=_cmd_mcp_inspect)

    p_scan = mcp_sub.add_parser("scan", help="安装前扫描目录模板（不写 mcp.yaml）")
    p_scan.add_argument("server_id")
    p_scan.set_defaults(func=_cmd_mcp_scan)

    p_test = mcp_sub.add_parser("test", help="探测已配置的 server")
    p_test.add_argument("server_id")
    p_test.set_defaults(func=_cmd_mcp_test)

    p_reload = mcp_sub.add_parser("reload", help="断开并重载 MCP 连接")
    p_reload.set_defaults(func=_cmd_mcp_reload)

    p_sync = mcp_sub.add_parser("sync", help="刷新 MCP SSOT 索引（合并视图）")
    p_sync.add_argument("--workspace", default="", help="项目工作区（写入 .butler/mcp-ssot.yaml）")
    p_sync.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    p_sync.add_argument("--reload", action="store_true", help="写入后重载 MCP 连接")
    p_sync.set_defaults(func=_cmd_mcp_sync)


def _cmd_mcp_search(ns: argparse.Namespace) -> int:
    svc = McpCatalogService()
    entries = svc.search(ns.query)
    print(svc.format_search(entries))
    return 0


def _cmd_mcp_add(ns: argparse.Namespace) -> int:
    ws = _workspace_from_ns(ns)
    use_project = bool(getattr(ns, "project", False)) or (
        ws is not None and not getattr(ns, "global_install", False)
    )
    if getattr(ns, "project", False) and ws is None:
        print("未解析到项目工作区，请使用 --workspace <path>")
        return 1
    ok, msg = install_catalog_server(
        ns.server_id,
        env_assignments=list(ns.env or []),
        workspace=ws,
        use_project=use_project and ws is not None,
    )
    print(msg)
    return 0 if ok else 1


def _cmd_mcp_remove(ns: argparse.Namespace) -> int:
    ws = _workspace_from_ns(ns) if getattr(ns, "workspace", "") else None
    ok, msg = remove_mcp_server(ns.server_id, workspace=ws)
    print(msg)
    return 0 if ok else 1


def _cmd_mcp_list(ns: argparse.Namespace) -> int:
    ws = _workspace_from_ns(ns)
    print(format_mcp_status_message(workspace=ws, include_catalog=True))
    return 0


def _cmd_mcp_status(ns: argparse.Namespace) -> int:
    ws = _workspace_from_ns(ns)
    print(format_mcp_status_message(workspace=ws, include_catalog=True))
    return 0


def _cmd_mcp_inspect(ns: argparse.Namespace) -> int:
    svc = McpCatalogService()
    entry = svc.get(ns.server_id)
    if entry is None:
        print(f"未找到目录项: {ns.server_id}")
        return 1
    print(svc.format_inspect(entry))
    return 0


def _cmd_mcp_scan(ns: argparse.Namespace) -> int:
    from butler.registry.install_scan import format_scan_message, pre_install_scan_mcp
    from butler.registry.mcp_install import _entry_to_server_block

    svc = McpCatalogService()
    entry = svc.get(ns.server_id)
    if entry is None:
        print(f"未找到目录项: {ns.server_id}")
        return 1
    block = _entry_to_server_block(entry, {})
    scan = pre_install_scan_mcp(entry, block)
    print(format_scan_message(scan))
    return 0 if scan.ok_to_install else 1


def _workspace_from_ns(ns: argparse.Namespace):
    raw = str(getattr(ns, "workspace", "") or "").strip()
    if raw:
        from pathlib import Path

        p = Path(raw).expanduser()
        return p if p.is_dir() else None
    return resolve_workspace_for_session()


def _cmd_mcp_test(ns: argparse.Namespace) -> int:
    import yaml

    from butler.registry.mcp_merge import find_server_config_path

    ws = _workspace_from_ns(ns) if getattr(ns, "workspace", "") else None
    path = find_server_config_path(ns.server_id, workspace=ws)
    if path is None:
        print("mcp.yaml 中未找到该 server")
        return 1
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    block = (data.get("servers") or {}).get(ns.server_id)
    if not block:
        print(f"未找到 server: {ns.server_id}")
        return 1
    probe = probe_server(ns.server_id, block)
    print(probe)
    return 0 if probe.get("ok") else 1


def _cmd_mcp_reload(ns: argparse.Namespace) -> int:
    ok, msg = reload_mcp_connections()
    print(msg)
    return 0 if ok else 1


def _cmd_mcp_sync(ns: argparse.Namespace) -> int:
    from butler.registry.mcp_ssot import sync_mcp_ssot

    ws = _workspace_from_ns(ns)
    ok, msg = sync_mcp_ssot(
        workspace=ws,
        dry_run=bool(getattr(ns, "dry_run", False)),
        reload=bool(getattr(ns, "reload", False)),
    )
    print(msg)
    return 0 if ok else 1
