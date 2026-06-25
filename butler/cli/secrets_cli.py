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


def cmd_secrets_encrypt(ns: argparse.Namespace) -> int:
    import json

    from butler.config_secrets import encrypt_secrets_file

    result = encrypt_secrets_file(dry_run=not bool(getattr(ns, "apply", False)))
    if bool(getattr(ns, "json", False)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result.get("ok"):
            print(result.get("error", "encrypt failed"), file=sys.stderr)
            return 1
        mode = "dry-run" if result.get("dry_run") else "applied"
        print(
            f"secrets encrypt ({mode}): changed={result.get('changed')} "
            f"encrypted={result.get('encrypted_after')}/{result.get('total_secrets')}"
        )
        if result.get("dry_run") and int(result.get("changed") or 0) > 0:
            print("加 --apply 写回加密后的 secrets.yaml", file=sys.stderr)
    return 0 if result.get("ok") else 1


def register_secrets_subparser(sub: argparse._SubParsersAction) -> None:
    sec = sub.add_parser("secrets", help="Provider API 密钥（secrets.yaml，不进 config.yaml）")
    sec_sub = sec.add_subparsers(dest="secrets_cmd", required=True)
    st = sec_sub.add_parser("set", help="写入 provider API key")
    st.add_argument("provider", help="如 minimax、openai")
    st.add_argument("api_key", help="API key 明文（仅本地）")
    st.set_defaults(func=cmd_secrets_set)
    stat = sec_sub.add_parser("status", help="显示 secrets.yaml 状态")
    stat.set_defaults(func=cmd_secrets_status)
    enc = sec_sub.add_parser("encrypt", help="将明文 provider key 加密为 FERNET:（需 BUTLER_SECRETS_ENCRYPT=1）")
    enc.add_argument("--apply", action="store_true", help="写回 secrets.yaml（默认 dry-run）")
    enc.add_argument("--json", action="store_true", help="输出 JSON")
    enc.set_defaults(func=cmd_secrets_encrypt)
