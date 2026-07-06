"""CLI: ``butler runtime ...`` — project scheduled jobs.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 subcommand
registration refactor. ``runtime`` parent + five subcommands
(``list`` / ``run`` / ``due`` / ``drain-push`` / ``approve``) were
inline in the old ``_build_parser``.
"""

from __future__ import annotations

import argparse
from typing import Any


def register_runtime_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``runtime`` parent with all sub-commands."""
    from butler import main as _butler_main

    rt = sub.add_parser("runtime", help="项目定时任务（cron/批准/微信推送）")
    rt_sub = rt.add_subparsers(dest="runtime_cmd", required=True)

    _add_runtime_list(rt_sub, _butler_main._cmd_runtime_list)
    _add_runtime_run(rt_sub, _butler_main._cmd_runtime_run)
    _add_runtime_due(rt_sub, _butler_main._cmd_runtime_due)
    _add_runtime_drain(rt_sub, _butler_main._cmd_runtime_drain_push)
    _add_runtime_approve(rt_sub, _butler_main._cmd_runtime_approve)


def _add_runtime_list(rt_sub: argparse._SubParsersAction[argparse.ArgumentParser], func: Any) -> None:
    p = rt_sub.add_parser("list", help="列出项目 runtime/jobs.yaml 任务")
    p.add_argument("--project", required=True, help="项目名称，如 灵文1号")
    p.set_defaults(func=func)


def _add_runtime_run(rt_sub: argparse._SubParsersAction[argparse.ArgumentParser], func: Any) -> None:
    p = rt_sub.add_parser("run", help="执行单个任务（改盘须已批准）")
    p.add_argument("job_id", help="jobs.yaml 中的 id")
    p.add_argument("--project", required=True)
    p.add_argument("--no-notify", action="store_true", help="不推送微信摘要")
    p.add_argument(
        "--force",
        action="store_true",
        help="允许运行 enabled:false 的任务（改盘仍须批准）",
    )
    p.set_defaults(func=func)


def _add_runtime_due(rt_sub: argparse._SubParsersAction[argparse.ArgumentParser], func: Any) -> None:
    p = rt_sub.add_parser("due", help="执行当前到期的任务（改盘仅推送待批准）")
    p.add_argument(
        "--project",
        default="灵文1号",
        help="项目名称；与 --all-projects 互斥",
    )
    p.add_argument(
        "--all-projects",
        action="store_true",
        help="扫描所有含 runtime/jobs.yaml 的项目",
    )
    p.add_argument("--no-notify", action="store_true", help="不推送微信摘要")
    p.set_defaults(func=func)


def _add_runtime_drain(rt_sub: argparse._SubParsersAction[argparse.ArgumentParser], func: Any) -> None:
    p = rt_sub.add_parser("drain-push", help="重试限流失败的微信推送队列")
    p.add_argument(
        "--max-items",
        type=int,
        default=3,
        help="最多重试条数（默认 3）",
    )
    p.set_defaults(func=func)


def _add_runtime_approve(rt_sub: argparse._SubParsersAction[argparse.ArgumentParser], func: Any) -> None:
    p = rt_sub.add_parser("approve", help="批准改盘任务并可立即执行")
    p.add_argument("job_id")
    p.add_argument("--project", required=True)
    p.add_argument(
        "--approve-only",
        action="store_true",
        help="仅写入批准，不立即执行",
    )
    p.add_argument("--no-notify", action="store_true")
    p.set_defaults(func=func)


def _cmd_runtime_list(ns: argparse.Namespace) -> int:
    from butler.runtime.service import format_jobs_list_text

    print(format_jobs_list_text(ns.project.strip()))
    return 0


def _cmd_runtime_run(ns: argparse.Namespace) -> int:
    from butler.runtime.service import run_job

    out = run_job(
        ns.project.strip(),
        ns.job_id.strip(),
        skip_notify=bool(ns.no_notify),
        force=bool(ns.force),
    )
    if out.get("error"):
        print(out["error"], file=__import__("sys").stderr)
        return 1
    status = "ok" if out.get("success") else "failed"
    print(f"[{status}] {out.get('job_id')}")
    if out.get("summary"):
        print(out["summary"])
    if out.get("record_path"):
        print(f"audit: {out['record_path']}")
    return 0 if out.get("success") else 2


def _cmd_runtime_due(ns: argparse.Namespace) -> int:
    from butler.runtime.service import run_due_jobs, run_due_jobs_all

    if getattr(ns, "all_projects", False):
        results = run_due_jobs_all(skip_notify=bool(ns.no_notify))
    else:
        results = run_due_jobs(
            ns.project.strip(),
            skip_notify=bool(ns.no_notify),
        )
    if not results:
        print("没有到期的任务。")
        return 0
    exit_code = 0
    for out in results:
        jid = out.get("job_id") or "?"
        proj = out.get("project")
        prefix = f"{proj}/{jid}" if proj else jid
        if out.get("error"):
            print(f"{prefix}: error — {out['error']}", file=__import__("sys").stderr)
            exit_code = 1
            continue
        if out.get("pending_approval"):
            note = "notified" if out.get("notified") else "skipped-notify-cooldown"
            print(f"{prefix}: [pending-approval] ({note})")
            continue
        status = "ok" if out.get("success") else "failed"
        print(f"{prefix}: [{status}]")
        if not out.get("success"):
            exit_code = 2
    return exit_code


def _cmd_runtime_drain_push(ns: argparse.Namespace) -> int:
    from butler.runtime.push_queue import drain_push_queue

    out = drain_push_queue(max_items=int(getattr(ns, "max_items", 3) or 3))
    skipped = out.get("skipped")
    if skipped == "rate_limit_cooldown":
        from butler.runtime.notify import rate_limit_drain_wait_seconds

        wait_s = rate_limit_drain_wait_seconds()
        print(
            f"推送队列: 跳过 drain（iLink 限流冷却中，约 {wait_s:.0f}s 后再试）, "
            f"剩余 {out.get('remaining', 0)}"
        )
        return 0
    print(
        f"推送队列: 尝试 {out.get('drained', 0)} 条, "
        f"成功 {out.get('sent', 0)}, 失败 {out.get('failed', 0)}, "
        f"剩余 {out.get('remaining', 0)}"
    )
    return 0 if not out.get("failed") else 2


def _cmd_runtime_approve(ns: argparse.Namespace) -> int:
    from butler.runtime.service import approve_and_run

    out = approve_and_run(
        ns.project.strip(),
        ns.job_id.strip(),
        run_now=not bool(ns.approve_only),
        skip_notify=bool(ns.no_notify),
    )
    if out.get("error"):
        print(out["error"], file=__import__("sys").stderr)
        return 1
    if out.get("message"):
        print(out["message"])
        return 0
    status = "ok" if out.get("success") else "failed"
    print(f"[{status}] {out.get('job_id')}")
    if out.get("summary"):
        print(out["summary"])
    return 0 if out.get("success") else 2
