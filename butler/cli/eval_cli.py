"""CLI: ``butler eval list|run|report|sync``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console


def _cmd_eval_list(_ns: argparse.Namespace) -> int:
    from butler.eval_integration.manager import EvalIntegrationManager

    console = Console()
    mgr = EvalIntegrationManager()
    for sid in mgr.list_suites():
        console.print(f"  {sid}")
    return 0


def _cmd_eval_run(ns: argparse.Namespace) -> int:
    from butler.eval_integration.manager import EvalIntegrationManager
    from butler.eval_integration.presets import resolve_suites

    console = Console()
    try:
        suites = resolve_suites(suite=ns.suite, preset=ns.preset)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    if not suites:
        console.print("[red]请指定 --suite 或 --preset[/red]")
        return 2
    mgr = EvalIntegrationManager()
    push_langfuse = False if ns.no_langfuse else None
    report, results = mgr.run_and_write(
        suites,
        out=Path(ns.out),
        warn_only=bool(ns.warn_only),
        sync_dataset=bool(ns.sync_dataset),
        push_langfuse=push_langfuse,
    )
    for r in results:
        status = "OK" if r.ok else "FAIL"
        console.print(f"  [{status}] {r.suite_id}")
    if not all(r.ok for r in results):
        return 1
    console.print(json.dumps(report.get("dimensions", {}), ensure_ascii=False, indent=2))
    console.print(f"-> {ns.out}")
    return 0


def _cmd_eval_report(ns: argparse.Namespace) -> int:
    from butler.eval_integration.manager import DEFAULT_REPORT, EvalIntegrationManager

    console = Console()
    path = Path(ns.out or DEFAULT_REPORT)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        console.print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    suites = [s.strip() for s in (ns.suite or "tcr").split(",") if s.strip()]
    mgr = EvalIntegrationManager()
    report, _ = mgr.run_and_write(suites, out=path, warn_only=True)
    console.print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _cmd_eval_sync(ns: argparse.Namespace) -> int:
    from butler.eval_integration.manager import EvalIntegrationManager

    console = Console()
    mgr = EvalIntegrationManager()
    sid = (ns.suite or "tcr").strip()
    out = mgr.sync_check(sid)
    console.print(json.dumps(out, ensure_ascii=False, indent=2))
    if out.get("warnings"):
        for w in out["warnings"]:
            console.print(f"[yellow]WARN[/yellow] {w}")
    if not out.get("ok") and not ns.warn_only:
        return 1
    return 0


def register_eval_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("eval", help="统一 Eval 接入管理（MOD-3）")
    ev = p.add_subparsers(dest="eval_cmd", required=True)

    ev.add_parser("list", help="列出已注册 suite").set_defaults(func=_cmd_eval_list)

    run_p = ev.add_parser("run", help="运行 suite 并写统一报告")
    run_p.add_argument("--suite", default="", help="逗号分隔 suite id")
    run_p.add_argument(
        "--preset",
        choices=["release", "weekly", "memory", "dev"],
        help="预设 suite 组合（与 --suite 二选一）",
    )
    run_p.add_argument(
        "--out",
        default=".butler/reports/eval-unified.json",
        help="EvalReport v1 输出路径",
    )
    run_p.add_argument("--warn-only", action="store_true", help="TCR 等 warn-only 模式")
    run_p.add_argument("--sync-dataset", action="store_true", help="regression 时同步 LangFuse dataset")
    run_p.add_argument("--no-langfuse", action="store_true", help="不向 LangFuse 推送")
    run_p.set_defaults(func=_cmd_eval_run)

    rep_p = ev.add_parser("report", help="打印或生成 EvalReport")
    rep_p.add_argument("--suite", default="tcr", help="生成时运行的 suite")
    rep_p.add_argument("--out", default="", help="报告路径")
    rep_p.set_defaults(func=_cmd_eval_report)

    sync_p = ev.add_parser("sync", help="多 sink 弱一致性检查")
    sync_p.add_argument("--suite", default="tcr")
    sync_p.add_argument("--warn-only", action="store_true", help="不一致时仍 exit 0")
    sync_p.set_defaults(func=_cmd_eval_sync)
