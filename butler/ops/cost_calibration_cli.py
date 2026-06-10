"""CLI for D4 cost calibration: report / set-baseline."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Butler D4 cost calibration")
    sub = parser.add_subparsers(dest="cmd", required=True)

    report_p = sub.add_parser("report", help="Show N-day rollup and baseline comparison")
    report_p.add_argument("--days", type=int, default=None)
    report_p.add_argument("--json", action="store_true", help="Machine-readable output")

    base_p = sub.add_parser("set-baseline", help="Record actual bill for comparison")
    base_p.add_argument("--usd", type=float, required=True, help="Actual bill USD")
    base_p.add_argument("--input-tokens", type=int, default=0)
    base_p.add_argument("--output-tokens", type=int, default=0)
    base_p.add_argument("--note", default="", help="e.g. MiniMax console week of 2026-06-01")

    args = parser.parse_args(argv)

    from butler.ops.cost_calibration import (
        compare_to_baseline,
        format_rollup_lines,
        load_baseline,
        rollup_period,
        save_baseline,
    )

    if args.cmd == "report":
        rollup = rollup_period(args.days)
        if args.json:
            payload = {
                "rollup": rollup.to_dict(),
                "baseline": load_baseline(),
                "comparison": compare_to_baseline(rollup, load_baseline()),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            lines = format_rollup_lines(rollup)
            if not lines:
                print("无成本事件（先运行会话或 BUTLER_COST_CALIBRATION_PERSIST=1）")
            else:
                print("\n".join(lines))
        return 0

    if args.cmd == "set-baseline":
        data = {
            "actual_usd": args.usd,
            "actual_input_tokens": args.input_tokens,
            "actual_output_tokens": args.output_tokens,
            "period_note": args.note,
        }
        path = save_baseline(data)
        print(f"基线已写入 {path}")
        rollup = rollup_period()
        cmp_ = compare_to_baseline(rollup, data)
        if cmp_.get("usd_deviation_pct") is not None:
            print(f"当前 {rollup.days} 日汇总 vs 基线 USD 偏差: {cmp_['usd_deviation_pct']:+.1f}%")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
