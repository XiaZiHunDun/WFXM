"""黑板 CLI 子命令：init / validate / snapshot / audit / handoff / sync。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from butler.blackboard import paths as bb_paths
from butler.blackboard.audit import audit_task
from butler.blackboard.handoff import build_handoff
from butler.blackboard.paths import configure_root
from butler.blackboard.shift_io import list_shift_cards
from butler.blackboard.snapshot import render_snapshot
from butler.blackboard.sync import sync_backlog_from_todos, sync_todos_from_backlog
from butler.blackboard.validator import parse_shift_card_file


def _root_arg(args: argparse.Namespace) -> None:
    if getattr(args, "root", None):
        configure_root(Path(args.root).resolve())


def cmd_init(args: argparse.Namespace) -> int:
    """建黑板目录 + 默认 README/state/log/空 backlog。"""
    _root_arg(args)
    bb_paths.BLACKBOARD_DIR.mkdir(parents=True, exist_ok=True)
    bb_paths.SHIFTS_DIR.mkdir(parents=True, exist_ok=True)
    bb_paths.CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    (bb_paths.CLAIMS_DIR / ".gitkeep").touch(exist_ok=True)
    (bb_paths.SHIFTS_DIR / ".gitkeep").touch(exist_ok=True)
    if not bb_paths.README_PATH.exists():
        bb_paths.README_PATH.write_text(
            "# BlackBoard\n\n"
            "Append-only shift cards coordinate heterogeneous agents.\n"
            "See docs/superpowers/specs/<latest-wfxm-blackboard-design>.md for the contract.\n",
            encoding="utf-8",
        )
    if not bb_paths.STATE_PATH.exists():
        bb_paths.STATE_PATH.write_text(
            "# WFXM BlackBoard State\n\n_last_synced: (init)_\n_last_shift: (none)_\n",
            encoding="utf-8",
        )
    (bb_paths.LOG_PATH).touch(exist_ok=True)
    if not bb_paths.BACKLOG_PATH.exists():
        bb_paths.BACKLOG_PATH.write_text(
            "schema_version: 1\nlast_updated: 1970-01-01T00:00:00+00:00\ntasks: []\n",
            encoding="utf-8",
        )
    print(f"initialized {bb_paths.BLACKBOARD_DIR}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """校验指定班次卡或 shifts/ 下所有卡。"""
    _root_arg(args)
    if args.shift_id:
        path = bb_paths.SHIFTS_DIR / f"{args.shift_id}.md"
        try:
            parse_shift_card_file(path)
        except Exception as exc:
            print(f"INVALID {args.shift_id}: {exc}", file=sys.stderr)
            return 1
        print(f"OK {args.shift_id}")
        return 0
    bad = 0
    for c in list_shift_cards():
        print(f"OK {c.shift_id}")
    if bad:
        return 1
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """从 shifts/tasks 派生新 state.md（写盘或 stdout）。"""
    _root_arg(args)
    md = render_snapshot()
    if args.dry_run:
        print(md)
    else:
        bb_paths.STATE_PATH.write_text(md, encoding="utf-8")
        print(f"updated {bb_paths.STATE_PATH}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    _root_arg(args)
    print(audit_task(args.task_id))
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    _root_arg(args)
    print(build_handoff(last_n=args.last_n))
    return 0


def cmd_sync_todos(args: argparse.Namespace) -> int:
    """Backlog ↔ ~/.butler/todos.json 同步。"""
    _root_arg(args)
    if args.from_todos:
        added = sync_todos_from_backlog()
        print(f"synced from todos: added {len(added)} task(s) → backlog.yaml")
        for tid in added:
            print(f"  + {tid}")
    else:
        n = sync_backlog_from_todos()
        print(f"synced backlog → todos.json: {n} item(s) updated")
    return 0


def register_blackboard_parser(sub: argparse._SubParsersAction) -> None:
    """注册 butler blackboard 顶层子命令。"""
    p = sub.add_parser(
        "blackboard",
        help="黑板体系子命令（init/validate/snapshot/audit/handoff/sync）",
    )
    bb_sub = p.add_subparsers(dest="blackboard_command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="黑板根目录（默认 CWD/.blackboard）")

    bb_sub.add_parser(
        "init", parents=[common], help="建黑板目录与默认文件"
    ).set_defaults(func=cmd_init)

    val = bb_sub.add_parser("validate", parents=[common], help="校验班次卡")
    val.add_argument("--shift-id", help="校验指定 ID；不传则校验 shifts/ 全部")
    val.set_defaults(func=cmd_validate)

    snap = bb_sub.add_parser("snapshot", parents=[common], help="派生 state.md")
    snap.add_argument("--dry-run", action="store_true", help="仅打印不写盘")
    snap.set_defaults(func=cmd_snapshot)

    aud = bb_sub.add_parser("audit", parents=[common], help="按 task_id 追溯班次")
    aud.add_argument("--task", dest="task_id", required=True)
    aud.set_defaults(func=cmd_audit)

    ho = bb_sub.add_parser("handoff", parents=[common], help="生成交接包")
    ho.add_argument("--last-n", type=int, default=3, help="包含最近几张班次卡")
    ho.set_defaults(func=cmd_handoff)

    sync = bb_sub.add_parser("sync-todos", parents=[common], help="同步 backlog ↔ ~/.butler/todos.json（默认 backlog→todos；--from-todos 反向）")
    sync.add_argument("--from-todos", action="store_true", help="反向：从 todos.json 拉新任务到 backlog.yaml")
    sync.set_defaults(func=cmd_sync_todos)