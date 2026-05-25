"""CLI: ``butler registry verify`` — catalog + hub manifest."""

from __future__ import annotations

import argparse


def register_registry_parser(sub: argparse._SubParsersAction) -> None:
    reg = sub.add_parser("registry", help="技能/MCP 目录与 manifest")
    sp = reg.add_subparsers(dest="registry_cmd", required=True)
    p_verify = sp.add_parser("verify", help="校验 bundled catalog 与远程 Hub 条目")
    p_verify.set_defaults(func=_cmd_verify)


def _cmd_verify(_ns: argparse.Namespace) -> int:
    from butler.registry.hub_manifest import format_hub_manifest_report, verify_hub_manifest

    report = verify_hub_manifest()
    print(format_hub_manifest_report(report))
    return 0 if report.ok else 1
