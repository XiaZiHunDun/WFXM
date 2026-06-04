"""Sprint 16 TST-10-5 第五批: butler.gateway.commands.project_commands 迁移测试.

迁移 4 个 inline 命令 (2 个独立 CommandDef + 2 个子命令入口):
  - /项目    (/projects)              → _cmd_project_list (含子命令 /项目 新建|体检)
  - /状态    (/status)                 → _cmd_butler_status
  - /项目 新建  (子命令, arg="新建 ...")  → 经 /项目 handler 委派到 handle_project_onboarding_command
  - /项目 体检  (子命令, arg="体检")      → 经 /项目 handler 委派到 handle_project_onboarding_command

注: /项目 新建 和 /项目 体检 在 registry 中不再作为独立 CommandDef (它们是 /项目
的子命令, cmd 永远是 /项目, 通过 arg 区分). 从 default 列表移除.

覆盖: 静态契约 + dispatch + 委派 + 子命令路由 + 死代码清理 + 集合缩小
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    all_commands,
    dispatch,
    lookup,
)
from butler.gateway.commands import project_commands as proj_cmds


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


def _make_ctx(
    cmd: str = "/项目",
    arg: str = "",
    *,
    orchestrator: MagicMock | None = None,
    platform: str = "wechat",
    external_id: str = "owner1",
    session_key: str = "wechat:chat1",
) -> CommandContext:
    return CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=orchestrator or MagicMock(),  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        session_registry=MagicMock(),  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
    )


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_2_handlers(self):
        for name in ("/项目", "/状态"):
            assert lookup(name) is not None, f"registry 缺 {name}"
            assert lookup(name).handler is not None, f"{name} 缺 handler"

    def test_module_defines_2_command_defs(self):
        from butler.gateway.commands.project_commands import _PROJECT_COMMANDS

        assert len(_PROJECT_COMMANDS) == 2
        for cmd in _PROJECT_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        for name in ("/项目", "/状态"):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler"

    def test_register_project_commands_is_idempotent(self):
        before = len(all_commands())
        proj_cmds.register_project_commands()
        after = len(all_commands())
        assert before == after

    def test_commands_init_imports_project_commands(self):
        from butler.gateway import commands as cmds_pkg

        assert "project_commands" in cmds_pkg.__all__
        assert hasattr(cmds_pkg, "project_commands")

    def test_dead_subcommand_entries_removed_from_default(self, ensure_registered):
        """/项目 体检 和 /项目 新建 不再是独立 CommandDef (它们是 /项目 的子命令)."""
        # 直接查 registry — 不应在 _REGISTRY 中独立存在
        from butler.gateway.command_registry import _REGISTRY

        assert "/项目 体检" not in _REGISTRY, (
            "/项目 体检 仍作为独立 CommandDef 存在 — 应合并到 /项目 的子命令"
        )
        assert "/项目 新建" not in _REGISTRY, (
            "/项目 新建 仍作为独立 CommandDef 存在 — 应合并到 /项目 的子命令"
        )


# ── dispatch + 别名 ──


class TestDispatch:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/projects", "/项目"),
            ("/status", "/状态"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        for name in ("/项目", "/状态"):
            ctx = _make_ctx(cmd=name)
            with patch(
                "butler.gateway.commands.project_commands.format_project_list",
                return_value="project-list-text",
            ) if name == "/项目" else patch(
                "butler.gateway.commands.project_commands.format_butler_status",
                return_value="status-text",
            ) as _handler:
                handled, result = dispatch(ctx)
            assert handled is True, f"{name} 仍走 inline"
            assert result is not None


# ── 行为委派 ──


class TestDelegation:
    def test_project_handler_calls_format_project_list(self, ensure_registered):
        """handler 应把 ctx 转给 format_project_list."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        orch = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        ctx = _make_ctx(
            cmd="/项目", arg="", orchestrator=orch, platform="wechat", external_id="owner1",
        )
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.commands.project_commands.format_project_list",
            return_value="list-text",
        ) as h:
            result = proj_cmds_module._cmd_project_list(ctx)
        assert result == "list-text"
        args, kwargs = h.call_args
        assert args[0] is orch  # orchestrator
        assert args[1] == "/项目"  # cmd
        assert args[2] == ""  # arg
        assert kwargs["session_key"] == "wechat:chat1"
        assert kwargs["platform"] == "wechat"
        assert kwargs["external_id"] == "owner1"

    def test_status_handler_calls_format_butler_status(self, ensure_registered):
        """handler 应把 ctx 转给 format_butler_status."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        orch = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        ctx = _make_ctx(cmd="/状态", orchestrator=orch)
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.commands.project_commands.format_butler_status",
            return_value="status-text",
        ) as h:
            result = proj_cmds_module._cmd_butler_status(ctx)
        assert result == "status-text"
        h.assert_called_once_with(orch, "wechat:chat1")

    def test_project_subcommand_arg_passed_through(self, ensure_registered):
        """/项目 handler 把 arg ("新建 foo" / "体检") 透传给 format_project_list."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        ctx = _make_ctx(cmd="/项目", arg="新建 myapp")
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.commands.project_commands.format_project_list",
            return_value="onboard-text",
        ) as h:
            proj_cmds_module._cmd_project_list(ctx)
        args, _ = h.call_args
        assert args[1] == "/项目"  # cmd
        assert args[2] == "新建 myapp"  # arg 不被改写

    def test_returns_none_when_handler_returns_none(self, ensure_registered):
        """format_project_list 返回 None → handler 返回 None (caller 决定下一步)."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        ctx = _make_ctx(cmd="/项目")
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.commands.project_commands.format_project_list",
            return_value=None,
        ):
            assert proj_cmds_module._cmd_project_list(ctx) is None


# ── /项目 子命令路由 (end-to-end, 走真实 format_project_list) ──


class TestSubcommandRouting:
    """/项目 handler 不解析子命令 — 委派给 handle_project_onboarding_command."""

    def test_新建_routed_to_onboarding(self, ensure_registered):
        """arg='新建 foo' → handle_project_onboarding_command 拦截, 返 onboard result."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        fake_pm = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        fake_pm.list_projects.return_value = []
        orch = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        orch.project_manager = fake_pm

        ctx = _make_ctx(cmd="/项目", arg="新建 myapp", orchestrator=orch)
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.project_commands.handle_project_onboarding_command",
            return_value="用法: /项目 新建 <slug> [模板]",
        ) as onboard:
            result = proj_cmds_module._cmd_project_list(ctx)
        assert result == "用法: /项目 新建 <slug> [模板]"
        onboard.assert_called_once()

    def test_体检_routed_to_onboarding(self, ensure_registered):
        """arg='体检' → handle_project_onboarding_command 拦截."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        fake_pm = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        fake_pm.list_projects.return_value = []
        orch = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        orch.project_manager = fake_pm

        ctx = _make_ctx(cmd="/项目", arg="体检", orchestrator=orch)
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.project_commands.handle_project_onboarding_command",
            return_value="预检报告: 全部通过",
        ) as onboard:
            result = proj_cmds_module._cmd_project_list(ctx)
        assert result == "预检报告: 全部通过"

    def test_no_arg_falls_through_to_list(self, ensure_registered):
        """arg='' → handle_project_onboarding_command 返 None, 落到 list 分支."""
        from butler.gateway.commands import project_commands as proj_cmds_module

        fake_pm = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        fake_pm.list_projects.return_value = []  # 空 → 返 '暂无项目。'
        orch = MagicMock()  # noqa: magicmock-no-spec — project status facade (orch / pm / session_registry)
        orch.project_manager = fake_pm

        ctx = _make_ctx(cmd="/项目", arg="", orchestrator=orch)
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True,
        ), patch(
            "butler.gateway.project_commands.handle_project_onboarding_command",
            return_value=None,
        ):
            result = proj_cmds_module._cmd_project_list(ctx)
        assert result == "暂无项目。"


# ── inline set 缩小 ──


class TestInlineSetShrink:
    def test_4_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/项目", "/项目 体检", "/项目 新建", "/状态"):
            assert name not in _KNOWN_INLINE_COMMANDS

    def test_inline_set_size_leq_12(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        # Sprint 16 baseline 16; 第五批迁移 4 个 → 12
        assert len(_KNOWN_INLINE_COMMANDS) <= 12
