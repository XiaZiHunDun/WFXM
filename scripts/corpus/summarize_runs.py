#!/usr/bin/env python3
"""Summarize corpus archive JSONL for issue-map / ops review.

Usage:
  python3 scripts/corpus/summarize_runs.py
  python3 scripts/corpus/summarize_runs.py --suite wechat_real.lw_real
  python3 scripts/corpus/summarize_runs.py --write docs/plans/corpus-issue-map-gateway-2026-05.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.corpus.harness.gateway_ops import (  # noqa: E402
    format_ops_markdown,
    production_inventory,
    summarize_archive,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize corpus archive runs")
    parser.add_argument(
        "--suite",
        default="wechat_real.lw_real",
        help="Filter by suite_id (default: wechat gateway)",
    )
    parser.add_argument(
        "--all-suites",
        action="store_true",
        help="Include all suites in archive (ignore --suite filter)",
    )
    parser.add_argument(
        "--write",
        metavar="PATH",
        help="Write markdown snapshot (append production + live sections)",
    )
    args = parser.parse_args()

    suite = None if args.all_suites else args.suite
    summary = summarize_archive(suite_id=suite)
    if args.all_suites:
        summary["suite_id"] = "(all suites)"

    inv = production_inventory()
    body = format_ops_markdown(summary, inventory=inv)

    if args.write:
        out = Path(args.write)
        if not out.is_absolute():
            out = ROOT / out
        header = (
            f"# 语料运营快照 — gateway ({date.today().isoformat()})\n\n"
            f"> 自动生成：`python3 scripts/corpus/summarize_runs.py --write {args.write}`\n\n"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(header + body + "\n", encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT)}")
    else:
        print(body)


if __name__ == "__main__":
    main()
