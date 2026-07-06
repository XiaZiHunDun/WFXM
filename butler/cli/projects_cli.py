"""CLI: ``butler projects`` / ``butler create`` / ``butler project ...``.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 subcommand
registration refactor. ``projects`` (list / reload), ``create``, and
the ``project`` parent with ``preflight`` / ``register`` subcommands
were inline in the old ``_build_parser``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def register_projects_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``projects``, ``create``, and the ``project`` parent."""
    _add_projects_top_parser(sub)
    _add_create_parser(sub)
    _add_project_parent_parser(sub)


def _add_projects_top_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # Late-bound func reference: tests patch ``butler.main._cmd_projects``
    # and expect the parser to pick up the mock. We read the function
    # from butler.main's namespace at registration time (which happens
    # inside main(), after the test has entered its ``patch`` context).
    from butler import main as _butler_main

    prj = sub.add_parser("projects", help="列出项目")
    prj.add_argument(
        "--reload",
        action="store_true",
        help="重新扫描 BUTLER_PROJECTS_DIR",
    )
    prj.set_defaults(func=_butler_main._cmd_projects)


def _add_create_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from butler import main as _butler_main

    cr = sub.add_parser("create", help="创建新项目（slug 目录名 + 可选中文显示名）")
    cr.add_argument("slug", help="ASCII 目录名，如 MyApp")
    cr.add_argument("--name", dest="display_name", default="", help="显示名（微信 /切换）")
    cr.add_argument("--type", dest="type_", default="software")
    cr.add_argument("--description", default="")
    cr.add_argument("--pack", default="", help="能力包，如 novel-factory")
    cr.add_argument(
        "--template",
        default="",
        help="模板 ID：software-default | novel-factory | knowledge-light",
    )
    cr.add_argument(
        "--no-runtime",
        action="store_true",
        help="不生成 runtime/jobs.yaml 模板",
    )
    cr.add_argument(
        "--reindex",
        action="store_true",
        help="创建后重建该项目 MEMORY 语义向量索引",
    )
    cr.set_defaults(func=_butler_main._cmd_create)


def _add_project_parent_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    pr = sub.add_parser("project", help="项目接入与体检")
    pr_sub = pr.add_subparsers(dest="project_cmd", required=True)
    _add_project_preflight_parser(pr_sub)
    _add_project_register_parser(pr_sub)


def _add_project_preflight_parser(pr_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from butler import main as _butler_main

    pf = pr_sub.add_parser("preflight", help="检查目录是否满足 Butler 项目接入条件")
    pf.add_argument(
        "--path",
        default="",
        help="工作区目录（含或即将写入 project.yaml）",
    )
    pf.add_argument(
        "--project",
        default="",
        help="已登记项目显示名（从 ProjectManager 解析 workspace）",
    )
    pf.add_argument("--json", action="store_true", help="输出 JSON（供脚本解析）")
    pf.set_defaults(func=_butler_main._cmd_project_preflight)


def _add_project_register_parser(pr_sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    from butler import main as _butler_main

    reg = pr_sub.add_parser("register", help="为已有目录登记 project.yaml")
    reg.add_argument("path", help="项目 workspace 目录")
    reg.add_argument("--name", dest="display_name", default="", help="覆盖显示名")
    reg.add_argument("--pack", default="")
    reg.add_argument(
        "--template",
        default="software-default",
        help="无 project.yaml 时使用的模板",
    )
    reg.add_argument(
        "--force-new-yaml",
        action="store_true",
        help="已有 project.yaml 时不合并，仅补 MEMORY",
    )
    reg.add_argument("--no-runtime", action="store_true", help="不生成 runtime/jobs.yaml")
    reg.add_argument("--reindex", action="store_true", help="登记后重建该项目 MEMORY 向量索引")
    reg.set_defaults(func=_butler_main._cmd_project_register)


def _cmd_projects(ns: argparse.Namespace) -> int:
    from butler.project.manager import get_project_manager

    manager = get_project_manager()
    if getattr(ns, "reload", False):
        return _cmd_projects_refresh(ns)
    projects = sorted(manager.list_projects(), key=lambda p: p.name)
    if not projects:
        print("No projects found.", file=sys.stderr)
        return 0
    current = manager.current_project
    for proj in projects:
        mark = "*" if proj.name == current else " "
        pack = getattr(proj, "pack", "") or ""
        extra = f" pack={pack}" if pack else ""
        print(f"[{mark}] {proj.name:20} ({proj.type:8}{extra})  {proj.workspace}")
    return 0


def _create_slug_from_ns(ns: argparse.Namespace) -> str:
    """CLI slug positional (legacy tests may still pass ``name``)."""
    return str(getattr(ns, "slug", None) or getattr(ns, "name", None) or "").strip()


def _cmd_create(ns: argparse.Namespace) -> int:
    from butler.project.manager import get_project_manager

    slug = _create_slug_from_ns(ns)
    if not slug:
        print("Error: missing project slug.", file=sys.stderr)
        return 2

    mgr = get_project_manager()
    try:
        created = mgr.create_project(
            slug,
            ns.type_,
            ns.description,
            display_name=(getattr(ns, "display_name", None) or "").strip() or slug,
            pack=(ns.pack or "").strip(),
            template=(ns.template or "").strip(),
            with_runtime=not ns.no_runtime,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if created is None:
        print(f"Project slug {slug!r} already exists.", file=sys.stderr)
        return 1
    print(f"Created project {created.name!r} at {created.workspace}")
    print(f"Next: butler project preflight --project {created.name!r}")
    if ns.reindex:
        from butler.project.archetypes import reindex_project_memory

        ok, msg = reindex_project_memory(created.name)
        print(f"Reindex: {msg}")
        return 0 if ok else 1
    print(f"      butler memory-reindex --project {created.name!r}")
    print("      (或 create/register 加 --reindex)")
    return 0


def _cmd_project_register(ns: argparse.Namespace) -> int:
    from butler.config import get_butler_settings
    from butler.project.manager import get_project_manager

    raw_path = ns.path.strip()
    if _is_git_url(raw_path):
        ok, resolved_or_msg = _clone_for_register(raw_path)
        if not ok:
            print(f"Git clone failed: {resolved_or_msg}", file=sys.stderr)
            return 1
        print(f"Cloned {raw_path} → {resolved_or_msg}")
        path = Path(resolved_or_msg)
    else:
        path = Path(raw_path).expanduser().resolve()
    mgr = get_project_manager()
    try:
        proj = mgr.register_workspace(
            path,
            display_name=(ns.display_name or "").strip(),
            pack=(ns.pack or "").strip(),
            template=(ns.template or "software-default").strip(),
            merge_existing=not ns.force_new_yaml,
            with_runtime=not ns.no_runtime,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    settings = get_butler_settings()
    under = path.resolve()
    try:
        under.relative_to(settings.projects_dir.resolve())
    except ValueError:
        print(
            f"Warning: {path} is outside BUTLER_PROJECTS_DIR ({settings.projects_dir})",
            file=sys.stderr,
        )
    print(f"Registered project {proj.name!r} at {proj.workspace}")
    print(f"Next: butler project preflight --project {proj.name!r}")
    if ns.reindex:
        from butler.project.archetypes import reindex_project_memory

        ok, msg = reindex_project_memory(proj.name)
        print(f"Reindex: {msg}")
        return 0 if ok else 1
    print("      butler projects --reload  # 若网关已运行")
    return 0


def _cmd_projects_refresh(_ns: argparse.Namespace) -> int:
    from butler.project.manager import get_project_manager

    mgr = get_project_manager()
    mgr.refresh()
    names = [p.name for p in mgr.list_projects()]
    print(f"Reloaded {len(names)} project(s): {', '.join(names) or '(none)'}")
    return 0


def _cmd_project_preflight(ns: argparse.Namespace) -> int:
    from butler.config import get_butler_settings
    from butler.project.preflight import (
        format_report,
        resolve_tool_safe_root,
        resolve_workspace,
        run_preflight,
    )

    settings = get_butler_settings()
    safe_root = resolve_tool_safe_root()

    ws = resolve_workspace(
        path=str(ns.path or ""),
        project_name=str(ns.project or ""),
        projects_dir=settings.projects_dir,
    )
    if ws is None:
        print(
            "用法: butler project preflight --path <目录>\n"
            "  或: butler project preflight --project <已登记项目名>",
            file=sys.stderr,
        )
        return 2

    report = run_preflight(
        ws,
        projects_dir=settings.projects_dir,
        safe_root=safe_root,
    )
    if ns.json:
        import json

        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


def _is_git_url(path: str) -> bool:
    """C1: support Git URL in CLI register (mirrors Gateway is_git_url)."""
    p = (path or "").strip()
    return p.startswith("https://") or p.startswith("git@")


def _clone_for_register(url: str) -> tuple[bool, str]:
    """Clone a Git repo into BUTLER_PROJECTS_DIR and return (ok, path_or_msg)."""
    import subprocess

    from butler.config import get_butler_settings

    settings = get_butler_settings()
    slug = url.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if slug.endswith(".git"):
        slug = slug[:-4]
    slug = slug or "repo"

    target = settings.projects_dir.expanduser().resolve() / slug
    if target.exists():
        return False, f"目标目录已存在: {target}"

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return False, result.stderr.strip() or f"git clone exited {result.returncode}"
        return True, str(target)
    except subprocess.TimeoutExpired:
        return False, "git clone timed out (300s)"
    except FileNotFoundError:
        return False, "git not found on PATH"
