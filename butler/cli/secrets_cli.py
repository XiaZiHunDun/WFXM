"""CLI: ``butler secrets set|status``."""

from __future__ import annotations

import argparse
import sys


def cmd_secrets_set(ns: argparse.Namespace) -> int:
    from butler.config_secrets import write_provider_secret

    provider = str(ns.provider or "").strip()
    key = str(ns.api_key or "").strip()
    if not provider or not key:
        print("用法: butler secrets set <provider> <api_key>", file=sys.stderr)
        return 2
    path = write_provider_secret(provider, key)
    print(f"已写入 {path}（权限 600，勿提交 git）")
    return 0


def cmd_secrets_status(_ns: argparse.Namespace) -> int:
    from butler.config_secrets import secrets_status_line

    print(secrets_status_line())
    return 0


def register_secrets_subparser(sub: argparse._SubParsersAction) -> None:
    sec = sub.add_parser("secrets", help="Provider API 密钥（secrets.yaml，不进 config.yaml）")
    sec_sub = sec.add_subparsers(dest="secrets_cmd", required=True)
    st = sec_sub.add_parser("set", help="写入 provider API key")
    st.add_argument("provider", help="如 minimax、openai")
    st.add_argument("api_key", help="API key 明文（仅本地）")
    st.set_defaults(func=cmd_secrets_set)
    stat = sec_sub.add_parser("status", help="显示 secrets.yaml 状态")
    stat.set_defaults(func=cmd_secrets_status)
