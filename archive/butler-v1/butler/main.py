"""Butler System entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_chat(args: argparse.Namespace) -> None:
    """Start interactive CLI chat with the butler."""
    setup_logging(args.verbose)

    from butler.config.settings import settings
    if args.projects_dir:
        settings.projects_dir = Path(args.projects_dir)

    from butler.gateway.cli_adapter import CLIAdapter

    adapter = CLIAdapter()
    asyncio.run(adapter.start())


def cmd_exec(args: argparse.Namespace) -> None:
    """Execute a single command and exit (non-interactive, for scripting)."""
    setup_logging(args.verbose)

    from butler.config.settings import settings
    if args.projects_dir:
        settings.projects_dir = Path(args.projects_dir)

    from butler.core.butler import Butler

    async def _run():
        butler = Butler(channel="cli")
        response = await butler.chat(args.message)
        print(response)
        await butler.close()

    asyncio.run(_run())


def cmd_gateway(args: argparse.Namespace) -> None:
    """Start the gateway server (WeChat, Telegram, etc.)."""
    setup_logging(args.verbose)

    from butler.config.settings import settings
    if args.projects_dir:
        settings.projects_dir = Path(args.projects_dir)

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    async def _run():
        adapters = []
        for platform in platforms:
            if platform == "wechat":
                from butler.gateway.wechat_adapter import WeChatAdapter
                adapters.append(WeChatAdapter())
            else:
                print(f"Unknown platform: {platform}")
                return

        for adapter in adapters:
            await adapter.start()

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            for adapter in adapters:
                await adapter.stop()

    asyncio.run(_run())


def cmd_wechat_setup(args: argparse.Namespace) -> None:
    """Run WeChat QR login setup wizard."""

    async def _run():
        from butler.gateway.wechat_adapter import qr_login
        creds = await qr_login()
        if creds:
            print(f"\n登录成功！")
            print(f"  Account ID: {creds['account_id']}")
            print(f"  Base URL:   {creds['base_url']}")
            print(f"\n凭证已保存。启动网关: butler gateway --platforms wechat")
            print(f"\n你也可以将以下环境变量添加到 .env:")
            print(f"  WEIXIN_ACCOUNT_ID={creds['account_id']}")
            print(f"  WEIXIN_TOKEN={creds['token']}")
            if creds['base_url'] != "https://ilinkai.weixin.qq.com":
                print(f"  WEIXIN_BASE_URL={creds['base_url']}")
        else:
            print("\n登录失败。")

    asyncio.run(_run())


def cmd_projects(args: argparse.Namespace) -> None:
    """List all projects."""
    from butler.config.settings import settings
    if args.projects_dir:
        settings.projects_dir = Path(args.projects_dir)

    from butler.core.project_manager import project_manager

    projects = project_manager.list_projects()
    if not projects:
        print("暂无项目。使用 `butler create <name>` 创建新项目。")
        return

    for p in projects:
        marker = " ★" if p.name == project_manager.current_project else ""
        print(f"  [{p.status}] {p.name} ({p.type}) - {p.description}{marker}")


def cmd_create(args: argparse.Namespace) -> None:
    """Create a new project."""
    from butler.config.settings import settings
    if args.projects_dir:
        settings.projects_dir = Path(args.projects_dir)

    from butler.core.project_manager import project_manager

    ok = project_manager.create_project(args.name, args.type, args.description)
    if ok:
        print(f"项目【{args.name}】已创建: {settings.projects_dir / args.name}")
    else:
        print(f"创建失败（可能已存在）: {args.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="butler",
        description="Butler System - 多项目 AI 协助系统",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    parser.add_argument("--projects-dir", type=str, default="", help="项目目录路径")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("chat", help="启动交互式对话").set_defaults(func=cmd_chat)

    exec_p = sub.add_parser("exec", help="执行单条指令")
    exec_p.add_argument("message", type=str, help="要执行的指令")
    exec_p.set_defaults(func=cmd_exec)

    gw_p = sub.add_parser("gateway", help="启动消息网关")
    gw_p.add_argument("--platforms", type=str, default="wechat", help="逗号分隔的平台列表")
    gw_p.set_defaults(func=cmd_gateway)

    sub.add_parser("wechat-setup", help="微信 QR 扫码登录").set_defaults(func=cmd_wechat_setup)

    sub.add_parser("projects", help="列出所有项目").set_defaults(func=cmd_projects)

    create_p = sub.add_parser("create", help="创建新项目")
    create_p.add_argument("name", type=str, help="项目名称")
    create_p.add_argument("--type", type=str, default="software", choices=["software", "content", "research"])
    create_p.add_argument("--description", type=str, default="")
    create_p.set_defaults(func=cmd_create)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        args.func = cmd_chat
        args.verbose = getattr(args, "verbose", False)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
