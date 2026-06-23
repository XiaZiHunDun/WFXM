"""Sprint 16 TST-10-5 第四批: 开发工具 inline 命令迁移.

迁移 6 个 dev 工具命令（统一走 handle_dev_command, 已含 owner gate）:
  - /git          → _cmd_dev_git
  - /测试         → _cmd_dev_test
  - /构建         → _cmd_dev_build
  - /开发状态     → _cmd_dev_status
  - /开发验收     → _cmd_dev_smoke
  - /项目概况     → _cmd_dev_project_dashboard
"""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register


def _dev_delegate(ctx: CommandContext) -> Optional[str]:
    """统一委派到 dev_handlers.handle_dev_command (含 owner gate)."""
    from butler.gateway.commands.dev_handlers import handle_dev_command

    return handle_dev_command(
        ctx.cmd,
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


_DEV_COMMANDS: list[CommandDef] = [
    CommandDef("/git", (), "开发工具", "Git 状态摘要", handler=_dev_delegate),
    CommandDef("/测试", ("/test",), "开发工具", "运行项目测试", handler=_dev_delegate),
    CommandDef("/构建", ("/build",), "开发工具", "运行项目构建", handler=_dev_delegate),
    CommandDef("/开发状态", ("/dev-status",), "开发工具", "开发环境概况", handler=_dev_delegate),
    CommandDef("/开发验收", ("/dev-smoke",), "开发工具", "跑开发冒烟测试", handler=_dev_delegate),
    CommandDef(
        "/项目概况",
        ("/project-dashboard",),
        "项目管理",
        "项目仪表盘（代码/任务/工具统计）",
        handler=_dev_delegate,
    ),
]


def register_dev_commands() -> None:
    """idempotent 注册 — 重复调用安全（register 内部覆盖）。"""
    for cmd in _DEV_COMMANDS:
        register(cmd)


# Import 时即注册, 与 lifecycle/dialog/info/memory/runtime 模式一致。
register_dev_commands()
