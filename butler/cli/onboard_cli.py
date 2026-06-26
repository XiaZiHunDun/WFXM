"""``butler onboard`` — deploy profile one-pager (PROD-P6-01)."""

from __future__ import annotations

import argparse


def register_onboard_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "onboard",
        help="部署剖面上手一页纸（必填 env + 下一步）",
    )
    p.add_argument(
        "--profile",
        choices=("gateway", "dev-local", "dev-remote"),
        default="",
        help="覆盖自动检测的 operating profile",
    )
    p.set_defaults(func=cmd_onboard)


def cmd_onboard(ns: argparse.Namespace) -> int:
    from butler.ops.onboard import format_onboard_report, resolve_onboard_profile

    prof = resolve_onboard_profile(ns.profile or "")
    print(format_onboard_report(profile=prof))
    return 0
