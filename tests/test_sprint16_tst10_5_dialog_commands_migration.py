"""Sprint 16 TST-10-5 第七批: butler.gateway.commands.dialog_commands 迁移测试.

迁移 3 个 inline 对话控制命令到 registry handler:
  - /切换     (/switch)        → _cmd_switch_project
  - /模型     (/model)         → _cmd_model_select
  - /新对话   (/new)           → _cmd_new_session

迁移要点:
  - 3 个命令都无 owner gate (与权限命令不同, 任何用户可切换项目/模型/重置会话)
  - 抽 format_switch_project_reply / format_model_reply / format_new_session_reply
    到 dialog_commands.py 作为可重用函数
  - 不再使用 _reset_tool_audit_events 私有别名, 改用 public
    butler.tools.tool_audit.reset_tool_audit_events
  - _KNOWN_INLINE_COMMANDS: 7 → 4
  - 既有 dialog_commands (8 owner-gated: steer/queue/确认/取消/循环/停止循环/计划/执行)
    与新增 3 个共存, 总 _DIALOG_COMMANDS: 8 → 11

覆盖: 静态契约 + dispatch + 委派 + 别名 + 副作用正确性 + 集合缩小
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
from butler.gateway.commands import dialog_commands as dialog_cmds


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


def _make_ctx(
    cmd: str = "/切换",
    arg: str = "",
    *,
    platform: str = "wechat",
    external_id: str = "u1",
    session_key: str = "wechat:u1:",
    orchestrator: MagicMock | None = None,
    session_registry: MagicMock | None = None,
) -> CommandContext:
    return CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=orchestrator or MagicMock(),  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        session_registry=session_registry or MagicMock(),  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
    )


def _make_pm_orch(
    *,
    switch_ok: bool = True,
    current_name: str = "default",
) -> MagicMock:
    """Build a mock orchestrator with project_manager."""
    pm = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
    pm.switch_project_for_chat.return_value = switch_ok
    pm.get_project_name_for_chat.return_value = current_name
    pm.list_projects.return_value = []
    pm.get_current.return_value = None
    pm.resolve_active_project_name.return_value = current_name
    orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
    orch.project_manager = pm
    return orch


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_3_new_handlers(self):
        for name in ("/切换", "/模型", "/新对话"):
            assert lookup(name) is not None, f"registry 缺 {name}"
            assert lookup(name).handler is not None, f"{name} 缺 handler"

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        for name in ("/切换", "/模型", "/新对话"):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler"

    def test_no_owner_gate_for_3_dialog_commands(self):
        """/切换 /模型 /新对话 应不需 owner gate (用户可自行执行)."""
        # 3 个 handler 函数体不调用 is_gateway_owner.
        import inspect

        for name, fn in (
            ("/切换", dialog_cmds._cmd_switch_project),
            ("/模型", dialog_cmds._cmd_model_select),
            ("/新对话", dialog_cmds._cmd_new_session),
        ):
            source = inspect.getsource(fn)
            assert "is_gateway_owner" not in source, (
                f"{name} 不应有 owner gate — 用户可自行切换/重置"
            )

    def test_total_dialog_commands_count_is_11(self):
        """/steer/queue/确认/取消/循环/停止循环/计划/执行 (8 existing) + 3 new = 11."""
        from butler.gateway.commands.dialog_commands import _DIALOG_COMMANDS

        assert len(_DIALOG_COMMANDS) == 11
        for cmd in _DIALOG_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None


# ── dispatch + 别名 ──


class TestDispatch:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/switch", "/切换"),
            ("/model", "/模型"),
            ("/new", "/新对话"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        for name in ("/切换", "/模型", "/新对话"):
            ctx = _make_ctx(cmd=name, arg="")
            handled, result = dispatch(ctx)
            assert handled is True, f"{name} 仍走 inline"
            # result 是字符串或 None (无 arg 时)
            assert result is None or isinstance(result, str)


# ── 行为委派: /切换 ──


class TestSwitchProject:
    def test_no_arg_returns_usage(self, ensure_registered):
        orch = _make_pm_orch()
        ctx = _make_ctx(cmd="/切换", arg="", orchestrator=orch)
        handled, result = dispatch(ctx)
        assert handled is True
        assert "用法" in result
        assert "/switch" in result

    def test_successful_switch_resets_sessions(self, ensure_registered):
        """switch_project_for_chat 返 True → reset_sessions_for_chat 应被调用."""
        orch = _make_pm_orch(switch_ok=True, current_name="beta")
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr.reset_sessions_for_chat.return_value = ["old-session-1", "old-session-2"]
        ctx = _make_ctx(cmd="/切换", arg="beta", orchestrator=orch, session_registry=sr)

        with patch(
            "butler.project.lead.lead_mode_switch_suffix", return_value="",
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert "已切换到项目: beta" in result
        assert "已重建对话引擎" in result
        assert "清理 2 个旧项目会话" in result
        orch.project_manager.switch_project_for_chat.assert_called_once()
        sr.reset_sessions_for_chat.assert_called_once()

    def test_successful_switch_no_cleared_sessions(self, ensure_registered):
        """reset_sessions_for_chat 返空 list → 不显示 '清理' 提示."""
        orch = _make_pm_orch(switch_ok=True, current_name="alpha")
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr.reset_sessions_for_chat.return_value = []
        ctx = _make_ctx(cmd="/切换", arg="alpha", orchestrator=orch, session_registry=sr)

        with patch(
            "butler.project.lead.lead_mode_switch_suffix", return_value="",
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert "已切换到项目: alpha" in result
        assert "清理" not in result

    def test_unknown_project_with_available(self, ensure_registered):
        """switch 返 False, 但有可用项目 → 列出可用项目."""
        orch = _make_pm_orch(switch_ok=False)
        proj_a = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        proj_a.name = "alpha"
        proj_b = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        proj_b.name = "beta"
        orch.project_manager.list_projects.return_value = [proj_a, proj_b]
        ctx = _make_ctx(cmd="/切换", arg="ghost", orchestrator=orch)
        handled, result = dispatch(ctx)
        assert handled is True
        assert "未找到项目: ghost" in result
        assert "alpha" in result
        assert "beta" in result
        assert "可用项目" in result

    def test_unknown_project_with_no_projects(self, ensure_registered):
        """switch 返 False, 也没项目 → 提示用 /项目 新建."""
        orch = _make_pm_orch(switch_ok=False)
        orch.project_manager.list_projects.return_value = []
        ctx = _make_ctx(cmd="/切换", arg="ghost", orchestrator=orch)
        handled, result = dispatch(ctx)
        assert handled is True
        assert "未找到项目: ghost" in result
        assert "/项目 新建" in result


# ── 行为委派: /模型 ──


class TestModelSelect:
    def test_dispatches_to_handle_model_command(self, ensure_registered):
        """handler 应把 ctx 转给 handle_model_command."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        orch = _make_pm_orch()
        ctx = _make_ctx(cmd="/模型", arg="gpt-4o", orchestrator=orch)
        with patch(
            "butler.model_resolve.handle_model_command",
            return_value=("切换成功: gpt-4o", False),  # no reset
        ) as h:
            handled, result = dispatch(ctx)
        assert handled is True
        assert result == "切换成功: gpt-4o"
        h.assert_called_once()
        args, kwargs = h.call_args
        assert args[0] == "gpt-4o"
        assert kwargs["project_label"] == "default"

    def test_model_change_triggers_session_reset(self, ensure_registered):
        """handle_model_command 返 (reply, True) → session_registry.reset 应被调."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        orch = _make_pm_orch()
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ctx = _make_ctx(cmd="/模型", arg="gpt-4o", orchestrator=orch, session_registry=sr)
        with patch(
            "butler.model_resolve.handle_model_command",
            return_value=("切换到 gpt-4o", True),  # reset_loop = True
        ), patch(
            "butler.tools.tool_audit.reset_tool_audit_events",
        ) as reset_audit:
            handled, result = dispatch(ctx)
        assert handled is True
        sr.reset.assert_called_once_with(ctx.session_key)
        reset_audit.assert_called_once_with(ctx.session_key)

    def test_no_reset_when_handle_returns_no_reset(self, ensure_registered):
        """handle_model_command 返 (reply, False) → 不 reset."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        orch = _make_pm_orch()
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ctx = _make_ctx(cmd="/模型", arg="", orchestrator=orch, session_registry=sr)
        with patch(
            "butler.model_resolve.handle_model_command",
            return_value=("当前模型: gpt-4o", False),
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        sr.reset.assert_not_called()


# ── 行为委派: /新对话 ──


class TestNewSession:
    def test_resets_session_and_cleans_state(self, ensure_registered):
        """/新对话 应: reset session + 11+ cleanup + 委派 handle_new_session_command."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        ctx_key = "wechat:u1:"
        orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        loop_mock = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr.sessions = {ctx_key: loop_mock}
        ctx = _make_ctx(
            cmd="/新对话", arg="", orchestrator=orch, session_registry=sr,
            session_key=ctx_key,
        )

        with patch(
            "butler.session.new_session.handle_new_session_command",
            return_value="已开始新对话",
        ) as h, patch.multiple(
            "butler.tools.tool_audit",
            reset_tool_audit_events=MagicMock(),  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ), patch.multiple(
            "butler.report",
            clear_report_cache=MagicMock(),  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ), patch.multiple(
            "butler.plan.mode",
            clear_plan_mode=MagicMock(),  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert result == "已开始新对话"
        # session_registry.reset 应被调用 (skip_finalize=True)
        sr.reset.assert_called_once_with(ctx.session_key, skip_finalize=True)
        # handle_new_session_command 应被调用, 传入 orchestrator + session_key + loop
        h.assert_called_once()
        h_args = h.call_args.args
        assert h_args[0] is orch
        assert h_args[1] == ctx.session_key
        assert h_args[2] is loop_mock  # loop from sessions dict

    def test_calls_optional_cleanup_modules(self, ensure_registered):
        """/新对话 应尝试调 11+ cleanup 函数 (部分模块可能不存在 → logger.debug + skip)."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        ctx = _make_ctx(
            cmd="/新对话", arg="", orchestrator=orch, session_registry=sr,
        )

        with patch(
            "butler.session.new_session.handle_new_session_command",
            return_value="ok",
        ):
            # 不应抛异常, 即使部分 cleanup 模块不存在
            handled, result = dispatch(ctx)
        assert handled is True
        # 主要 cleanup: session_registry.reset 应被调
        sr.reset.assert_called_once_with(ctx.session_key, skip_finalize=True)

    def test_session_registry_sessions_dict_accessed(self, ensure_registered):
        """ctx.session_registry.sessions 应被访问以获取 loop."""
        from butler.gateway.commands import dialog_commands as dialog_cmds_module

        ctx_key = "wechat:u1:"
        orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        loop_mock = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr.sessions = {ctx_key: loop_mock}
        ctx = _make_ctx(
            cmd="/新对话", arg="", orchestrator=orch, session_registry=sr,
            session_key=ctx_key,
        )
        with patch(
            "butler.session.new_session.handle_new_session_command",
            return_value="ok",
        ) as h:
            dispatch(ctx)
        # loop 应被传入 handle_new_session_command
        assert h.call_args.args[2] is loop_mock


# ── 错误处理 (registry 集中处理) ──


class TestErrorHandling:
    def test_switch_handler_exception_returns_error(self, ensure_registered):
        """switch_project_for_chat 抛异常 → dispatch 返 '命令执行异常: ...'."""
        orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        orch.project_manager.switch_project_for_chat.side_effect = RuntimeError("boom")
        ctx = _make_ctx(cmd="/切换", arg="alpha", orchestrator=orch)
        handled, result = dispatch(ctx)
        assert handled is True
        assert "命令执行异常" in result
        assert "boom" in result

    def test_model_handler_exception_returns_error(self, ensure_registered):
        """handle_model_command 抛异常 → dispatch 返 '命令执行异常: ...'."""
        orch = _make_pm_orch()
        ctx = _make_ctx(cmd="/模型", arg="x", orchestrator=orch)
        with patch(
            "butler.model_resolve.handle_model_command",
            side_effect=RuntimeError("model-fail"),
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert "命令执行异常" in result
        assert "model-fail" in result

    def test_new_session_handler_exception_returns_error(self, ensure_registered):
        """handle_new_session_command 抛异常 → dispatch 返 '命令执行异常: ...'."""
        orch = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr = MagicMock()  # noqa: magicmock-no-spec — dialog command facade (ProjectManager / SessionRegistry / orch)
        sr.sessions = {}
        ctx = _make_ctx(
            cmd="/新对话", arg="", orchestrator=orch, session_registry=sr,
        )
        with patch(
            "butler.session.new_session.handle_new_session_command",
            side_effect=RuntimeError("ns-fail"),
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert "命令执行异常" in result
        assert "ns-fail" in result


# ── inline set 缩小 ──


class TestInlineSetShrink:
    def test_3_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/切换", "/模型", "/新对话"):
            assert name not in _KNOWN_INLINE_COMMANDS

    def test_inline_set_size_leq_4(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        # Sprint 16 baseline 7; 第七批迁移 3 个 → 4
        assert len(_KNOWN_INLINE_COMMANDS) <= 4
