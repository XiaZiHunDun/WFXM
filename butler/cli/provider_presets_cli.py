"""CLI: ``butler provider`` preset commands."""

from __future__ import annotations

import argparse


def register_provider_presets_parser(sub: argparse._SubParsersAction) -> None:
    prov = sub.add_parser("provider", help="模型 provider 预设（butler://）")
    sp = prov.add_subparsers(dest="provider_cmd", required=True)
    p_list = sp.add_parser("presets", help="列出 butler:// 预设")
    p_list.set_defaults(func=_cmd_presets)


def _cmd_presets(_ns: argparse.Namespace) -> int:
    from butler.provider_presets import format_presets_list

    print(format_presets_list())
    return 0
