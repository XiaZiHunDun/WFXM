"""CLI: ``butler memory ...`` + ``butler memory-reindex ...``.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 subcommand
registration refactor. Both ``memory`` (with ``search`` / ``reindex``
subcommands) and the legacy top-level ``memory-reindex`` command were
inline in the old ``_build_parser``.
"""

from __future__ import annotations

import argparse

from rich.console import Console


def register_memory_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``memory`` (with subcommands) and ``memory-reindex``."""
    from butler import main as _butler_main

    mem = sub.add_parser("memory", help="本地记忆检索与语义索引")
    mem_sub = mem.add_subparsers(dest="memory_cmd", required=True)
    _register_memory_subcommands(mem_sub, _butler_main)

    ri = sub.add_parser(
        "memory-reindex",
        help="重建本地语义向量索引（需 BUTLER_SEMANTIC_MEMORY=1，无云存储）",
    )
    _add_reindex_args(ri)
    ri.set_defaults(func=_butler_main._cmd_memory_reindex)


def _register_memory_subcommands(mem_sub: argparse._SubParsersAction, _butler_main) -> None:
    _register_memory_search_reindex(mem_sub, _butler_main)
    _register_memory_ops_parsers(mem_sub)
    _register_memory_migrate_parsers(mem_sub)


def _register_memory_search_reindex(mem_sub: argparse._SubParsersAction, _butler_main) -> None:
    msearch = mem_sub.add_parser(
        "search",
        help="检索 experience / 项目 MEMORY（--verbose 输出 fallback 与分数分解）",
    )
    _add_search_args(msearch)
    msearch.set_defaults(func=_butler_main._cmd_memory_search)

    mreindex = mem_sub.add_parser(
        "reindex",
        help="重建本地语义向量索引（需 BUTLER_SEMANTIC_MEMORY=1）",
    )
    _add_reindex_args(mreindex)
    mreindex.set_defaults(func=_butler_main._cmd_memory_reindex)


def _register_memory_ops_parsers(mem_sub: argparse._SubParsersAction) -> None:
    mseed = mem_sub.add_parser(
        "seed",
        help="清理 MB5 bench filler 并幂等写入 owner 经验指针种子",
    )
    mseed.add_argument("--tenant", default="default", help="租户 id（默认 default）")
    mseed.add_argument(
        "--seed-path",
        default="",
        help="种子 JSON 路径（默认 data/seed_owner_experiences.json）",
    )
    mseed.add_argument(
        "--no-purge",
        action="store_true",
        help="跳过 bench/cap filler 清理",
    )
    mseed.set_defaults(func=_cmd_memory_seed)

    mgc = mem_sub.add_parser(
        "gc",
        help="扫描并清理 experience 向量孤儿（默认 dry-run）",
    )
    mgc.add_argument("--tenant", default="default", help="租户 id（默认 default）")
    mgc.add_argument(
        "--apply",
        action="store_true",
        help="执行删除（默认仅报告）",
    )
    mgc.set_defaults(func=_cmd_memory_gc)

    mdiagnose = mem_sub.add_parser(
        "diagnose",
        help="六层记忆作用域快照（L3/L4 编码经验 + 生产 lesson）",
    )
    mdiagnose.add_argument(
        "--project",
        default="",
        help="项目注册名（空=租户 L4 + 各项目 L3 概览）",
    )
    mdiagnose.add_argument("--tenant", default="default", help="租户 id（预留）")
    mdiagnose.add_argument("--json", action="store_true", help="输出 JSON")
    mdiagnose.set_defaults(func=_cmd_memory_diagnose)


def _register_memory_migrate_parsers(mem_sub: argparse._SubParsersAction) -> None:
    mbackfill = mem_sub.add_parser(
        "backfill-scopes",
        help="将 legacy L4 编码经验推断的 MemoryScope 写回 JSON（P5）",
    )
    mbackfill.add_argument(
        "--apply",
        action="store_true",
        help="写回 ~/.butler/coding_experiences.json（默认 dry-run）",
    )
    mbackfill.set_defaults(func=_cmd_memory_backfill_scopes)

    mmigrate = mem_sub.add_parser(
        "migrate-lingwen-l3",
        help="将灵文 private B9 经验从 L4 迁到项目 L3",
    )
    mmigrate.add_argument(
        "--apply",
        action="store_true",
        help="写回 L4/L3 JSON（默认 dry-run）",
    )
    mmigrate.set_defaults(func=_cmd_memory_migrate_lingwen_l3)

    mmerge = mem_sub.add_parser(
        "merge-pending",
        help="查看/应用/驳回经验向量近邻合并待审队列",
    )
    mmerge.add_argument(
        "--apply",
        metavar="KEY",
        default="",
        help="将待审项合并写入已有 experience 行",
    )
    mmerge.add_argument(
        "--dismiss",
        metavar="KEY",
        default="",
        help="从待审队列移除（不写入）",
    )
    mmerge.add_argument("--json", action="store_true", help="输出 JSON")
    mmerge.set_defaults(func=_cmd_memory_merge_pending)


def _add_search_args(msearch: argparse.ArgumentParser) -> None:
    msearch.add_argument("query", help="检索词")
    msearch.add_argument(
        "--scope",
        choices=("experience", "project", "profile"),
        default="experience",
        help="experience=跨项目经验; project=当前/指定项目 MEMORY; profile=Owner 画像向量",
    )
    msearch.add_argument(
        "--project",
        default="",
        help="experience 范围的项目过滤，或 project 范围的项目名",
    )
    msearch.add_argument("--limit", type=int, default=8, help="最多返回条数（1–20）")
    msearch.add_argument("--tenant", default="default", help="租户 id（默认 default）")
    msearch.add_argument(
        "--verbose",
        action="store_true",
        help="打印 chunk_id、source_path、score_breakdown、检索模式",
    )
    msearch.add_argument(
        "--json",
        action="store_true",
        help="输出完整 JSON（含结构化字段）",
    )


def _add_reindex_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tenant", default="default", help="租户 id（默认 default）")
    p.add_argument(
        "--project",
        default="",
        help="仅重建指定项目名的 MEMORY.md 条目（空=扫描 BUTLER_PROJECTS_DIR 下全部）",
    )
    p.add_argument(
        "--experience-only",
        action="store_true",
        help="只索引 experience.db，跳过项目 MEMORY",
    )
    p.add_argument(
        "--no-clear",
        action="store_true",
        help="不清空现有向量表（增量 upsert，可能残留已删条目）",
    )


def _cmd_memory_search(ns: argparse.Namespace) -> int:
    from butler.config import get_butler_home
    from butler.memory.search_cli import format_search_json, run_memory_search

    payload = run_memory_search(
        get_butler_home(),
        str(ns.query or ""),
        scope=str(ns.scope or "experience"),
        limit=int(ns.limit or 8),
        project=str(ns.project or ""),
        tenant=str(ns.tenant or "default"),
        verbose=bool(ns.verbose),
        json_out=bool(ns.json),
    )
    if bool(ns.json):
        print(format_search_json(payload))
    if not payload.get("ok"):
        return 1
    return 0


def _cmd_memory_seed(ns: argparse.Namespace) -> int:
    import json
    from pathlib import Path

    from butler.config import get_butler_home
    from butler.memory.owner_experience_seed import run_owner_experience_seed

    seed_path = Path(ns.seed_path).expanduser() if str(ns.seed_path or "").strip() else None
    result = run_owner_experience_seed(
        get_butler_home(),
        tenant_id=str(ns.tenant or "default"),
        seed_path=seed_path,
        purge_filler=not bool(ns.no_purge),
    )
    console = Console()
    console.print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_memory_gc(ns: argparse.Namespace) -> int:
    import json

    from butler.config import get_butler_home
    from butler.memory.vector_gc import run_memory_gc

    result = run_memory_gc(
        get_butler_home(),
        tenant_id=str(ns.tenant or "default"),
        apply=bool(ns.apply),
    )
    console = Console()
    console.print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 1
    if result.get("dry_run"):
        orphans = int(result.get("orphan_experience_vectors") or 0)
        conv = int(result.get("conversation_vectors") or 0)
        if orphans or conv:
            console.print(
                "[yellow]dry-run：加 --apply 执行删除；"
                "大范围陈旧仍建议 butler memory reindex[/yellow]"
            )
    return 0


def _cmd_memory_diagnose(ns: argparse.Namespace) -> int:
    import json

    from butler.config import get_butler_home
    from butler.memory.scope_diagnostics import run_memory_scope_diagnose

    payload = run_memory_scope_diagnose(
        butler_home=get_butler_home(),
        project=str(ns.project or ""),
        json_out=bool(ns.json),
    )
    if bool(ns.json):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console = Console()
        for line in payload.get("lines") or []:
            console.print(line)
    return 0 if payload.get("ok") else 1


def _cmd_memory_backfill_scopes(ns: argparse.Namespace) -> int:
    import json

    from butler.config import get_butler_home
    from butler.memory.scope_diagnostics import backfill_tenant_coding_scopes

    result = backfill_tenant_coding_scopes(
        butler_home=get_butler_home(),
        dry_run=not bool(ns.apply),
    )
    console = Console()
    console.print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 1
    if result.get("dry_run") and int(result.get("updated") or 0) > 0:
        console.print("[yellow]dry-run：加 --apply 写回 L4 scope 字段[/yellow]")
    return 0


def _cmd_memory_migrate_lingwen_l3(ns: argparse.Namespace) -> int:
    import json

    from butler.config import get_butler_home
    from butler.dev_engine.prod_delegate_bridge import migrate_lingwen_experiences_to_l3

    result = migrate_lingwen_experiences_to_l3(
        butler_home=get_butler_home(),
        dry_run=not bool(ns.apply),
    )
    console = Console()
    console.print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        return 1
    if result.get("dry_run") and result.get("migrated"):
        console.print("[yellow]dry-run：加 --apply 执行 L4→L3 迁移[/yellow]")
    return 0


def _merge_pending_emit(result: dict, *, json_out: bool, ok_label: str, err_default: str) -> int:
    import json

    from rich.console import Console

    if json_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        console = Console()
        if result.get("ok"):
            console.print(ok_label)
        else:
            console.print(f"[red]{result.get('error', err_default)}[/red]")
    return 0 if result.get("ok") else 1


def _cmd_memory_merge_pending(ns: argparse.Namespace) -> int:
    from butler.config import get_butler_home
    from butler.memory.experience_consolidation import (
        apply_merge_pending,
        dismiss_merge_pending,
        format_merge_pending_report,
        load_merge_pending,
    )

    apply_key = str(ns.apply or "").strip()
    dismiss_key = str(ns.dismiss or "").strip()
    if apply_key and dismiss_key:
        from rich.console import Console

        Console().print("[red]不能同时指定 --apply 与 --dismiss[/red]")
        return 1

    if apply_key:
        result = apply_merge_pending(apply_key, butler_home=get_butler_home())
        label = (
            f"[green]已合并[/green] key={result.get('key')} "
            f"id={result.get('row_id')} sim={result.get('similarity')}"
        )
        return _merge_pending_emit(
            result, json_out=bool(ns.json), ok_label=label, err_default="apply failed",
        )

    if dismiss_key:
        result = dismiss_merge_pending(dismiss_key)
        label = f"[yellow]已驳回[/yellow] key={result.get('key')}"
        return _merge_pending_emit(
            result, json_out=bool(ns.json), ok_label=label, err_default="dismiss failed",
        )

    pending = load_merge_pending()
    if bool(ns.json):
        import json

        print(json.dumps({"ok": True, "count": len(pending), "entries": pending}, ensure_ascii=False, indent=2))
        return 0

    from rich.console import Console

    for line in format_merge_pending_report(pending):
        Console().print(line)
    return 0


def _cmd_memory_reindex(ns: argparse.Namespace) -> int:
    from butler.config import get_butler_home
    from butler.memory.reindex import ensure_semantic_enabled_msg, reindex_semantic_memory

    hint = ensure_semantic_enabled_msg()
    if hint:
        console = Console()
        console.print(f"[yellow]{hint}[/yellow]")
        return 2

    result = reindex_semantic_memory(
        get_butler_home(),
        tenant_id=str(ns.tenant or "default"),
        project_name=(ns.project or "").strip() or None,
        index_experience=True,
        index_project_memory=not ns.experience_only,
        clear_vectors=not ns.no_clear,
    )
    console = Console()
    if not result.get("ok"):
        console.print(f"[red]{result.get('error', 'reindex failed')}[/red]")
        return 1
    console.print(
        "[bold]语义向量索引已重建[/bold]\n"
        f"  租户: {result.get('tenant_id')}\n"
        f"  模型: {result.get('model_id')}\n"
        f"  清空旧条: {result.get('cleared', 0)}\n"
        f"  experience: {result.get('indexed_experience', 0)} "
        f"(跳过 conversation {result.get('skipped_conversation', 0)})\n"
        f"  项目 MEMORY 条目: {result.get('indexed_project_bullets', 0)} "
        f"(扫描项目 {result.get('projects_scanned', 0)})\n"
        f"  Markdown 层级块: {result.get('indexed_markdown_chunks', 0)}\n"
        f"  向量表合计: {result.get('vector_rows', 0)}"
    )
    return 0
