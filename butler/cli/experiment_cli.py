"""CLI: ``butler experiment list|record|best|discard``."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console


def _resolve_workspace(project: str) -> tuple[Path | None, str | None]:
    name = (project or "").strip()
    if not name:
        return None, "请指定 --project"
    from butler.project.manager import get_project_manager

    proj = get_project_manager().get_project(name)
    if proj is None:
        return None, f"未知项目: {name}"
    return Path(proj.workspace), None


def _cmd_experiment_list(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.ledger import experiments_ledger_path, list_recent

    path = experiments_ledger_path(ws)
    rows = list_recent(ws, limit=int(ns.limit or 10))
    if not rows:
        console.print(f"无记录: {path}")
        return 0
    console.print(f"[bold]实验账本[/bold] {path}")
    for row in rows:
        console.print(
            f"  {row.get('timestamp', '')} | {row.get('status', '?')} | "
            f"{row.get('metric_name')}={row.get('metric_value')} | "
            f"sha={str(row.get('git_sha') or '')[:12]} | "
            f"{(row.get('hypothesis') or '')[:60]}"
        )
    return 0


def _cmd_experiment_record(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.ledger import append_record

    try:
        val = float(ns.metric_value)
    except (TypeError, ValueError):
        console.print("[red]--metric-value 须为数字[/red]")
        return 1
    path = append_record(
        ws,
        metric_name=str(ns.metric_name or "score"),
        metric_value=val,
        status=str(ns.status or "keep"),
        hypothesis=str(ns.hypothesis or ""),
        cost_mb=str(ns.cost_mb or ""),
        git_sha=str(ns.git_sha or ""),
        job_id=str(ns.job_id or ""),
    )
    console.print(f"[green]已写入[/green] {path}")
    return 0


def _cmd_experiment_best(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.ledger import best_record

    row = best_record(ws, metric_name=str(ns.metric_name or ""))
    if row is None:
        console.print("无 keep 记录")
        return 0
    console.print(
        f"最佳: {row.get('metric_name')}={row.get('metric_value')} "
        f"sha={row.get('git_sha')} @ {row.get('timestamp')}"
    )
    return 0


def _cmd_experiment_discard(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.git_utils import git_reset_hard
    from butler.experiments.ledger import append_record, best_record

    best = best_record(ws, metric_name=str(ns.metric_name or ""))
    sha = str(ns.git_sha or (best or {}).get("git_sha") or "").strip()
    if not sha:
        console.print("[red]无目标 sha（指定 --git-sha 或先有 keep 记录）[/red]")
        return 1
    append_record(
        ws,
        metric_name=str(ns.metric_name or (best or {}).get("metric_name") or "score"),
        metric_value=float((best or {}).get("metric_value") or 0),
        status="discard",
        hypothesis=str(ns.hypothesis or "manual discard"),
    )
    if ns.apply_reset:
        ok, msg = git_reset_hard(ws, sha)
        if ok:
            console.print(f"[green]{msg}[/green]")
        else:
            console.print(f"[red]{msg}[/red]")
            return 1
    else:
        console.print(
            "已记 discard（未 reset）；加 --apply-reset 且 "
            f"BUTLER_EXPERIMENT_GIT_RESET=1 可回滚到 {sha[:12]}"
        )
    return 0


def register_experiment_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    exp = sub.add_parser("experiment", help="实验账本（harness / METRIC / keep-discard）")
    exp_sub = exp.add_subparsers(dest="experiment_cmd", required=True)

    lst = exp_sub.add_parser("list", help="列出最近实验行")
    lst.add_argument("--project", required=True)
    lst.add_argument("--limit", type=int, default=10)
    lst.set_defaults(func=_cmd_experiment_list)

    rec = exp_sub.add_parser("record", help="手动写入一行")
    rec.add_argument("--project", required=True)
    rec.add_argument("--metric-name", default="score")
    rec.add_argument("--metric-value", required=True)
    rec.add_argument("--status", default="keep", choices=("keep", "discard", "crash"))
    rec.add_argument("--hypothesis", default="")
    rec.add_argument("--cost-mb", default="")
    rec.add_argument("--git-sha", default="")
    rec.add_argument("--job-id", default="")
    rec.set_defaults(func=_cmd_experiment_record)

    best = exp_sub.add_parser("best", help="显示最佳 keep 行")
    best.add_argument("--project", required=True)
    best.add_argument("--metric-name", default="")
    best.set_defaults(func=_cmd_experiment_best)

    disc = exp_sub.add_parser("discard", help="记 discard；可选 git reset 到 best/指定 sha")
    disc.add_argument("--project", required=True)
    disc.add_argument("--metric-name", default="")
    disc.add_argument("--git-sha", default="")
    disc.add_argument("--hypothesis", default="")
    disc.add_argument(
        "--apply-reset",
        action="store_true",
        help="BUTLER_EXPERIMENT_GIT_RESET=1 时执行 git reset --hard",
    )
    disc.set_defaults(func=_cmd_experiment_discard)

    oc = exp_sub.add_parser("outcome", help="结果日志 pending/resolve")
    oc_sub = oc.add_subparsers(dest="outcome_cmd", required=True)

    oc_list = oc_sub.add_parser("list", help="列出 pending")
    oc_list.add_argument("--project", required=True)
    oc_list.set_defaults(func=_cmd_outcome_list)

    oc_res = oc_sub.add_parser("resolve", help="标记 resolved")
    oc_res.add_argument("--project", required=True)
    oc_res.add_argument("--row-id", required=True)
    oc_res.add_argument("--value", required=True)
    oc_res.add_argument("--reflection", default="")
    oc_res.set_defaults(func=_cmd_outcome_resolve)


def _cmd_outcome_list(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.outcomes import list_pending, outcomes_path

    rows = list_pending(ws, project=str(ns.project or ""), limit=20)
    if not rows:
        console.print(f"无 pending: {outcomes_path(ws)}")
        return 0
    for r in rows:
        console.print(
            f"  {r.get('row_id')} | {r.get('subject')} | {r.get('hypothesis', '')[:50]}"
        )
    return 0


def _cmd_outcome_resolve(ns: argparse.Namespace) -> int:
    console = Console()
    ws, err = _resolve_workspace(ns.project)
    if err:
        console.print(f"[red]{err}[/red]")
        return 1
    from butler.experiments.outcomes import resolve_outcome

    row = resolve_outcome(
        ws,
        row_id=str(ns.row_id),
        outcome_value=str(ns.value),
        reflection=str(ns.reflection or ""),
        project=str(ns.project or ""),
    )
    if row is None:
        console.print("[red]未找到 pending 行[/red]")
        return 1
    console.print(f"[green]已 resolved[/green] {row.get('reflection', '')[:120]}")
    return 0
