"""CLI: ``butler gateway`` + ``butler wechat-setup`` — WeChat iLink entry points.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 subcommand
registration refactor. ``gateway`` (start the WeChat-only gateway) and
``wechat-setup`` (QR login wizard) were inline in the old
``_build_parser``.

Helpers ``_print_wechat_setup_success`` and ``_merge_wechat_env_file``
travel with the command — they are only used by ``_cmd_wechat_setup``
and have no other consumers in main.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast


def register_gateway_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``gateway`` and ``wechat-setup``."""
    gw = sub.add_parser("gateway", help="启动微信消息网关（iLink，仅此平台）")
    gw.add_argument(
        "--platforms",
        default="",
        help="仅支持 wechat（默认）；其他平台名将被拒绝",
    )
    gw.add_argument(
        "gateway_remainder",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    gw.set_defaults(func=_cmd_gateway)

    wx = sub.add_parser(
        "wechat-setup",
        help="微信 iLink 扫码绑定 Bot（保存到 ~/.butler/wechat/accounts/）",
    )
    wx.add_argument("--timeout", type=int, default=480, help="扫码等待秒数（默认 480）")
    wx.add_argument("--bot-type", default="3", help="iLink bot_type 参数（默认 3）")
    wx.add_argument(
        "--write-env",
        nargs="?",
        const=".env",
        default=None,
        metavar="PATH",
        help="将 WECHAT_ACCOUNT_ID/WECHAT_TOKEN 写入 .env（默认项目根 .env）",
    )
    wx.set_defaults(func=_cmd_wechat_setup)


def _cmd_gateway(ns: argparse.Namespace) -> int:
    """Start WeChat-only Butler gateway (iLink)."""
    remainder = list(getattr(ns, "gateway_remainder", None) or [])
    legacy = [x for x in remainder if x in ("--hermes-fallback", "--native-only")]
    if legacy:
        print(
            "Butler 网关仅支持微信，已移除 --hermes-fallback / --native-only。"
            "请使用: butler gateway",
            file=sys.stderr,
        )
        return 2

    from butler.gateway.platform_policy import (
        format_unsupported_error,
        normalize_platforms,
        unsupported_platforms,
    )
    from butler.gateway.runner import run_gateway_blocking

    platforms = normalize_platforms(ns.platforms or "")
    bad = unsupported_platforms(platforms)
    if bad:
        print(format_unsupported_error(bad), file=sys.stderr)
        return 2
    return cast(int, run_gateway_blocking(["wechat"]))


def _cmd_wechat_setup(ns: argparse.Namespace) -> int:
    """Interactive WeChat iLink QR login (Hermes-style setup wizard)."""
    import asyncio

    from butler.config import get_butler_home
    from butler.gateway.platforms.wechat import check_wechat_requirements, qr_login

    if not check_wechat_requirements():
        print(
            "微信扫码需要可选依赖: pip install -e \".[wechat]\"",
            file=sys.stderr,
        )
        return 1

    async def _run() -> dict[str, str] | None:
        return cast(
            dict[str, str] | None,
            await qr_login(
                str(get_butler_home()),
                bot_type=str(getattr(ns, "bot_type", "3") or "3"),
                timeout_seconds=int(getattr(ns, "timeout", 480) or 480),
            ),
        )

    try:
        creds = asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130

    if not creds:
        print("登录失败或超时。", file=sys.stderr)
        return 1

    _print_wechat_setup_success(creds)

    write_env = getattr(ns, "write_env", None)
    if write_env is not None:
        from butler.repo_paths import REPO_ROOT

        env_path = Path(write_env) if str(write_env).strip() else REPO_ROOT / ".env"
        if not env_path.is_absolute():
            env_path = (REPO_ROOT / env_path).resolve()
        _merge_wechat_env_file(env_path, creds)

    return 0


def _print_wechat_setup_success(creds: dict[str, str]) -> None:
    """Human-readable next steps after QR login."""
    account_id = creds["account_id"]
    token = creds["token"]
    base_url = creds.get("base_url") or "https://ilinkai.weixin.qq.com"
    print("\n微信 iLink 绑定成功。")
    print(f"  Account ID: {account_id}")
    print(f"  Base URL:   {base_url}")
    print(f"\n凭证已写入 ~/.butler/wechat/accounts/{account_id}.json")
    print("\n启动网关:")
    print("  butler gateway")
    print("  # 生产推荐: bash scripts/install-butler-gateway-service.sh")
    print("  # 日常: bash scripts/butler-gateway-ops.sh restart")
    masked_token = token[:6] + "…" + token[-4:] if len(token) > 12 else "***"
    print(
        "\n可将以下内容加入项目 .env（也可只设 WECHAT_ACCOUNT_ID，"
        "token 会从 accounts 目录读取）:"
    )
    print(f"WECHAT_ACCOUNT_ID={account_id}")
    print(f"WECHAT_TOKEN={masked_token}  # 完整 token 已存入 ~/.butler/wechat/accounts/")
    if base_url != "https://ilinkai.weixin.qq.com":
        print(f"WECHAT_BASE_URL={base_url}")
    print("\n勿与 Hermes 共用同一 Bot；Hermes 凭证在 ~/.hermes/，Butler 在 ~/.butler/。")


def _merge_wechat_env_file(env_path: Path, creds: dict[str, str]) -> None:
    """Upsert WECHAT_* lines in a dotenv file."""
    base_url = creds.get("base_url") or "https://ilinkai.weixin.qq.com"
    updates = {
        "WECHAT_ACCOUNT_ID": creds["account_id"],
        "WECHAT_TOKEN": creds["token"],
        "WEIXIN_ACCOUNT_ID": creds["account_id"],
        "WEIXIN_TOKEN": creds["token"],
    }
    if base_url != "https://ilinkai.weixin.qq.com":
        updates["WECHAT_BASE_URL"] = base_url
        updates["WEIXIN_BASE_URL"] = base_url

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = (
            line.split("=", 1)[0].strip()
            if "=" in line and not line.lstrip().startswith("#")
            else ""
        )
        if key in updates:
            if key not in seen:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            continue
        out.append(line)

    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"\n已更新 {env_path}")
