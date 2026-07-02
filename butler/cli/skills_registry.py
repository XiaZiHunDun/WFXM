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

    p_sync = sp.add_parser(
        "sync",
        help="刷新 SSOT 索引，或将租户 registry 技能同步到项目 .butler/skills",
    )
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument(
        "--project",
        default="",
        metavar="WORKSPACE",
        help="项目 workspace；将 lockfile 技能从租户目录复制到 .butler/skills",
    )
    p_sync.add_argument(
        "--only",
        default="",
        help="仅同步指定技能名（逗号分隔）；默认读 stack.yaml skills_expected ∩ lockfile",
    )
    p_sync.set_defaults(func=_cmd_sync)

    p_lint = sp.add_parser("lint", help="检查技能 frontmatter（warn 不阻断）")
    p_lint.add_argument(
        "--project",
        default="",
        help="项目 workspace 路径（默认仅租户全局 skills）",
    )
    p_lint.set_defaults(func=_cmd_lint)

    p_learn = sp.add_parser("learn", help="受控技能学习（auxiliary LLM → 待审或直写）")
    p_learn.add_argument("description", help="技能用途描述（≥8 字）")
    p_learn.add_argument(
        "--project",
        default="",
        help="项目 workspace；技能写入 .butler/skills（默认租户全局）",
    )
    p_learn.set_defaults(func=_cmd_learn)

    p_pending = sp.add_parser("pending", help="列出待批准技能（BUTLER_SKILL_WRITE_APPROVAL）")
    p_pending.set_defaults(func=_cmd_pending)

    p_appr = sp.add_parser("approve", help="批准待审技能")
    p_appr.add_argument("index", nargs="?", default="", help="序号（1-based）或 all")
    p_appr.set_defaults(func=_cmd_approve)

    p_rej = sp.add_parser("reject", help="拒绝待审技能")
    p_rej.add_argument("index", nargs="?", default="", help="序号（1-based）或 all")
    p_rej.set_defaults(func=_cmd_reject)


def _skill_manager_for_cli(*, project: str = ""):
    from pathlib import Path

    from butler.config import load_settings
    from butler.skills.manager import SkillManager
    from butler.tenant import tenant_skills_dir

    settings = load_settings()
    tenant_id = _tenant_id()
    global_dir = tenant_skills_dir(settings.butler_home, tenant_id)
    project_ws = (project or "").strip()
    if project_ws:
        proj_skills = Path(project_ws).expanduser().resolve() / ".butler" / "skills"
        return SkillManager(skills_dir=proj_skills, global_skills_dir=global_dir)
    return SkillManager(skills_dir=global_dir, global_skills_dir=None)


def _tenant_id() -> str:
    from butler.cli.skills_registry_ops import default_tenant_id_safe

    return default_tenant_id_safe()


def _cmd_search(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    hits = svc.search(ns.query, source_filter=ns.source, limit=ns.limit)
    print(svc.format_search_table(hits))
    return 0


def _cmd_install(ns: argparse.Namespace) -> int:
    from butler.cli.skills_registry_ops import run_skill_install_cli

    svc = SkillRegistryService(tenant_id=_tenant_id())
    code, message, rec = run_skill_install_cli(
        svc,
        identifier=ns.identifier,
        name_override=ns.name or "",
        force=bool(ns.force),
        confirmed=bool(ns.yes) or bool(ns.force),
    )
    if code != 0:
        if message:
            print(message)
        return code
    print(f"已安装: {rec.name} → {rec.install_path} ({rec.scan_verdict})")
    followup = svc.install_followup(ns.identifier, record=rec)
    if followup:
        print(followup)
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
    ident = target if ("/" in target or target.startswith("clawhub:") or target.startswith("marketplace:")) else rec.identifier
    followup = svc.install_followup(ident, record=rec)
    if followup:
        print(followup)
    return 0


def _cmd_sync(ns: argparse.Namespace) -> int:
    project = (getattr(ns, "project", "") or "").strip()
    if project:
        from butler.registry.skills_project_sync import sync_tenant_skills_to_project

        only_raw = (getattr(ns, "only", "") or "").strip()
        only = [s.strip() for s in only_raw.split(",") if s.strip()] or None
        ok, msg, actions = sync_tenant_skills_to_project(
            project,
            tenant_id=_tenant_id(),
            only=only,
            dry_run=bool(getattr(ns, "dry_run", False)),
        )
        print(msg)
        for line in actions:
            print(f"  • {line}")
        return 0 if ok else 1

    from butler.registry.skills_ssot import sync_skills_ssot

    ok, msg = sync_skills_ssot(
        tenant_id=_tenant_id(),
        dry_run=bool(getattr(ns, "dry_run", False)),
    )
    print(msg)
    return 0 if ok else 1


def _cmd_list(ns: argparse.Namespace) -> int:
    svc = SkillRegistryService(tenant_id=_tenant_id())
    rows = svc.list_installed()
    if not rows:
        print("（无 registry 安装记录）")
        return 0
    for r in rows:
        print(f"• {r.name} [{r.source}] {r.identifier} ({r.scan_verdict})")
    return 0


def _cmd_lint(ns: argparse.Namespace) -> int:
    from pathlib import Path

    from butler.config import load_settings
    from butler.skills.lint import format_lint_report, lint_skill_summaries
    from butler.skills.manager import SkillManager
    from butler.tenant import tenant_skills_dir

    settings = load_settings()
    tenant_id = _tenant_id()
    global_dir = tenant_skills_dir(settings.butler_home, tenant_id)
    project_ws = (ns.project or "").strip()
    if project_ws:
        proj_skills = Path(project_ws).expanduser().resolve() / ".butler" / "skills"
        mgr = SkillManager(skills_dir=proj_skills, global_skills_dir=global_dir)
    else:
        mgr = SkillManager(skills_dir=global_dir, global_skills_dir=None)
    issues = lint_skill_summaries(mgr.list_skills())
    print(format_lint_report(issues))
    return 1 if issues else 0


def _cmd_learn(ns: argparse.Namespace) -> int:
    from butler.skills.learn import run_skill_learn

    mgr = _skill_manager_for_cli(project=getattr(ns, "project", "") or "")
    result = run_skill_learn(ns.description, mgr)
    if not result.get("ok"):
        print(result.get("error") or "技能学习失败")
        return 1
    print(result.get("message") or "完成")
    return 0


def _cmd_pending(ns: argparse.Namespace) -> int:
    from butler.skills.write_approval import format_skill_pending_lines

    lines = format_skill_pending_lines()
    if not lines:
        print("（无待审技能）")
        return 0
    print("\n".join(lines))
    return 0


def _cmd_approve(ns: argparse.Namespace) -> int:
    from butler.skills.write_approval import (
        approve_all_skill_pending,
        approve_skill_pending,
        list_skill_pending,
    )

    mgr = _skill_manager_for_cli()
    key = (ns.index or "").strip().lower()
    if key in ("全部", "all", "*", ""):
        if key == "":
            print("用法: butler skills approve <序号>  或  butler skills approve all")
            return 1
        count = approve_all_skill_pending(mgr)
        print(f"已批准 {count} 条")
        return 0
    try:
        idx = int(key) - 1
    except ValueError:
        print("序号必须是数字")
        return 1
    if not list_skill_pending():
        print("无待审技能")
        return 1
    result = approve_skill_pending(idx, mgr)
    if result.get("ok"):
        print(f"已批准: {result.get('name')} ({result.get('outcome')})")
        return 0
    print(f"失败: {result.get('error')}")
    return 1


def _cmd_reject(ns: argparse.Namespace) -> int:
    from butler.skills.write_approval import (
        list_skill_pending,
        reject_all_skill_pending,
        reject_skill_pending,
    )

    key = (ns.index or "").strip().lower()
    if key in ("全部", "all", "*", ""):
        if key == "":
            print("用法: butler skills reject <序号>  或  butler skills reject all")
            return 1
        count = reject_all_skill_pending()
        print(f"已拒绝 {count} 条")
        return 0
    try:
        idx = int(key) - 1
    except ValueError:
        print("序号必须是数字")
        return 1
    if reject_skill_pending(idx):
        print(f"已拒绝第 {idx + 1} 条")
        return 0
    print("拒绝失败")
    return 1
