"""CLI: ``butler cost ...`` — D4 cost calibration (report / set-baseline)."""

from __future__ import annotations

import argparse
from typing import cast


def register_cost_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    cost = sub.add_parser("cost", help="成本标定：汇总报告与账单基线对照")
    cost_sub = cost.add_subparsers(dest="cost_cmd", required=True)

    report_p = cost_sub.add_parser("report", help="N 日汇总与基线偏差")
    report_p.add_argument("--days", type=int, default=None)
    report_p.add_argument("--json", action="store_true")
    report_p.set_defaults(func=_cmd_cost_report)

    base_p = cost_sub.add_parser("set-baseline", help="录入控制台账单基线")
    base_p.add_argument("--usd", type=float, required=True)
    base_p.add_argument("--input-tokens", type=int, default=0)
    base_p.add_argument("--output-tokens", type=int, default=0)
    base_p.add_argument("--note", default="")
    base_p.set_defaults(func=_cmd_cost_set_baseline)


def _cmd_cost_report(ns: argparse.Namespace) -> int:
    from butler.ops.cost_calibration_cli import main as cal_main

    argv = ["report"]
    if ns.days is not None:
        argv.extend(["--days", str(ns.days)])
    if ns.json:
        argv.append("--json")
    return cast(int, cal_main(argv))


def _cmd_cost_set_baseline(ns: argparse.Namespace) -> int:
    from butler.ops.cost_calibration_cli import main as cal_main

    argv = [
        "set-baseline",
        "--usd",
        str(ns.usd),
        "--input-tokens",
        str(ns.input_tokens),
        "--output-tokens",
        str(ns.output_tokens),
    ]
    if ns.note:
        argv.extend(["--note", ns.note])
    return cast(int, cal_main(argv))
