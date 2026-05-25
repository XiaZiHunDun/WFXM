"""CLI: butler skills search|install|uninstall|list."""

from __future__ import annotations

import argparse

from butler.registry.skill_service import SkillRegistryService


def register_skills_parser(sub: argparse._SubParsersAction) -> None:
    skills = sub.add_parser("skills", help="技能目录：搜索 / 安装 / 卸载")
    sp = skills.add_subparsers(dest="skills_cmd", required=True)

    p_search = sp.add_parser("search", help="搜索技能")
    p_search.add_argument("query", nargs="?", default="")
    p_search.add_argument("--source", default="all")
    p_search.add_argument("--limit", type=int, default=20)
    p_search.set_defaults(func=_cmd_search)

    p_ins = sp.add_parser("install", help="安装技能到租户 skills 目录")
    p_ins.add_argument("identifier")
    p_ins.add_argument("--name", default="", help="覆盖技能名")
    p_ins.add_argument("--force", action="store_true")
    p_ins.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过 community 源确认（等同 confirmed）",
    )
    p_ins.set_defaults(func=_cmd_install)

    p_un = sp.add_parser("uninstall", help="卸载 registry 安装的技能")
    p_un.add_argument("name")
    p_un.set_defaults(func=_cmd_uninstall)

    p_list = sp.add_parser("list", help="列出已安装（lockfile）")
    p_list.set_defaults(func=_cmd_list)

    p_inspect = sp.add_parser("inspect", help="查看技能元数据")
    p_inspect.add_argument("identifier")
    p_inspect.set_defaults(func=_cmd_inspect)

    p_up = sp.add_parser("upgrade", help="升级已安装的 registry 技能")
    p_up.add_argument("target", nargs="?", default="", help="名称或 identifier")
    p_up.add_argument("--force", action="store_true", default=True)
    p_up.set_defaults(func=_cmd_upgrade)


def _tenant_id() -> str:
    try:
        from butler.config import load_settings

        return load_settings().default_tenant
    except Exception:
        return "default"


def _cmd_search(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    hits = svc.search(ns.query, source_filter=ns.source, limit=ns.limit)
    print(svc.format_search_table(hits))
    return 0


def _cmd_install(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    try:
        rec = svc.install(
            ns.identifier,
            name_override=ns.name or "",
            force=bool(ns.force),
            confirmed=bool(ns.yes) or bool(ns.force),
        )
    except Exception as exc:
        from butler.registry.registry_errors import InstallConfirmationRequired

        if isinstance(exc, InstallConfirmationRequired):
            h = exc.hit
            print(
                f"需要确认安装 [{h.source}/{h.trust}]: {h.name}\n"
                f"  id: {h.identifier}\n"
                f"重试: butler skills install {h.identifier} --yes"
            )
            return 2
        if isinstance(exc, ValueError):
            print(f"安装失败: {exc}")
            return 1
        raise
    print(f"已安装: {rec.name} → {rec.install_path} ({rec.scan_verdict})")
    return 0


def _cmd_uninstall(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    ok, msg = svc.uninstall(ns.name)
    print(msg)
    return 0 if ok else 1


def _cmd_inspect(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    hit = svc.inspect(ns.identifier)
    if not hit:
        print(f"未找到: {ns.identifier}")
        return 1
    print(f"名称: {hit.name}")
    print(f"来源: {hit.source} ({hit.trust})")
    print(f"ID: {hit.identifier}")
    print(f"描述: {hit.description}")
    if hit.extra:
        for k, v in hit.extra.items():
            print(f"  {k}: {v}")
    return 0


def _cmd_upgrade(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    target = (ns.target or "").strip()
    if not target:
        print("用法: butler skills upgrade <name|identifier>")
        return 1
    try:
        if "/" in target or target.startswith("clawhub:") or target.startswith("http"):
            rec = svc.upgrade(identifier=target, force=bool(ns.force))
        else:
            rec = svc.upgrade(name=target, force=bool(ns.force))
    except ValueError as exc:
        print(f"升级失败: {exc}")
        return 1
    print(f"已升级: {rec.name} ({rec.content_hash})")
    return 0


def _cmd_list(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    rows = svc.list_installed()
    if not rows:
        print("（无 registry 安装记录）")
        return 0
    for r in rows:
        print(f"• {r.name} [{r.source}] {r.identifier} ({r.scan_verdict})")
    return 0
