"""CLI for D3-6 experience mining."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Butler D3-6 experience mining")
    sub = parser.add_subparsers(dest="cmd", required=True)

    mine_p = sub.add_parser("mine", help="Run mining + review pipeline")
    mine_p.add_argument("--workspace", type=Path, default=None)
    mine_p.add_argument("--days", type=int, default=None)
    mine_p.add_argument("--auto-ingest", action="store_true")
    mine_p.add_argument("--json", action="store_true")

    sub.add_parser("pending", help="List pending candidates")

    appr_p = sub.add_parser("approve", help="Approve pending candidates into library")
    appr_p.add_argument("ids", nargs="*", help="Candidate ids (prefix match ok)")
    appr_p.add_argument("--all", action="store_true")

    args = parser.parse_args(argv)

    from butler.memory.experience_mining import (
        approve_pending,
        format_pending_lines,
        format_pipeline_report,
        load_pending,
        run_pipeline,
    )

    if args.cmd == "mine":
        result = run_pipeline(
            args.workspace,
            days=args.days,
            auto_ingest=args.auto_ingest,
        )
        if args.json:
            print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
        else:
            print(format_pipeline_report(result))
        return 0

    if args.cmd == "pending":
        print("\n".join(format_pending_lines(limit=20)))
        return 0

    if args.cmd == "approve":
        ids: list[str] | None = None
        if not args.all and args.ids:
            pending = load_pending()
            resolved: list[str] = []
            for token in args.ids:
                token = token.strip().lower()
                for cid in pending:
                    if cid.lower().startswith(token) or token in cid.lower():
                        resolved.append(cid)
            ids = resolved
        counts = approve_pending(ids, approve_all=args.all)
        print(
            f"批准 {counts['approved']} 条 · 入库 {counts['added']} · 跳过 {counts['skipped']}"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
