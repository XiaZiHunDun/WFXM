"""Sprint 16 TST-11-3: butler.gateway.commands.lifecycle_commands 覆盖 21% → 高覆盖.

bug: butler/gateway/commands/lifecycle_commands.py 262 行
  - 11 handler 中仅 ``_cmd_config`` 有测试, 其余 10 个 0%
  - 11 个命令: /doctor /导出 /回滚 /分叉 /记忆提炼 /确认安装 /技能 /mcp /config /任务 /工作流

修复: 直接补单测覆盖各 handler 的 owner gate + happy path + 错误分支,
       不改实现 (实现已正确, 只是没测)。
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.command_registry import CommandContext
from butler.gateway.commands import lifecycle_commands


# ── 通用 fixture: 让 owner gate 通过 + 提供最小 ctx ──


@pytest.fixture
def owner_env(monkeypatch):
    """让 is_gateway_owner 返回 True (BUTLER_PROJECT_CREATE_OPEN=1)。"""
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")


@pytest.fixture
def non_owner_env(monkeypatch):
    """让 is_gateway_owner 返回 False: platform 不在 wechat/weixin, 且没 allowlist。"""
    # 默认 BUTLER_PROJECT_CREATE_OPEN 未设, owner_wechat_ids() 空, 平台 non-wechat
    monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)


def _make_ctx(
    *,
    cmd: str = "/doctor",
    arg: str = "",
    session_key: str = "test:user1",
    platform: str = "wechat",
    external_id: str = "u-owner",
    orchestrator: object = None,
    session_registry: object = None,
) -> CommandContext:
    """构造一个最小可用的 CommandContext。"""
    return CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=orchestrator,
        session_registry=session_registry,
    )


# ── /doctor ──


class TestCmdDoctor:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        """非 owner 调 /doctor → 返回 owner_required_message。"""
        ctx = _make_ctx(platform="telegram", external_id="anyone")
        result = lifecycle_commands._cmd_doctor(ctx)
        assert result is not None
        assert "主公" in result or "Owner" in result

    def test_happy_path_returns_audit_report(self, owner_env):
        """owner 调 /doctor → 调 run_security_audit + format_audit_report, 返回 report。"""
        ctx = _make_ctx()
        fake_findings: list = []
        with patch("butler.ops.security_audit.run_security_audit", return_value=fake_findings), \
             patch("butler.ops.security_audit.format_audit_report", return_value="(mock audit report)") as fmt:
            result = lifecycle_commands._cmd_doctor(ctx)
        assert result == "(mock audit report)"
        fmt.assert_called_once_with(fake_findings)

    def test_workspace_passed_when_project_resolves(self, owner_env):
        """ctx 有 project → workspace 传给 run_security_audit。"""
        from pathlib import Path

        fake_proj = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_proj.workspace = "/tmp/ws"
        fake_pm = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_pm.get_current.return_value = fake_proj
        fake_orch = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_orch.project_manager = fake_pm
        ctx = _make_ctx(orchestrator=fake_orch)

        with patch("butler.ops.security_audit.run_security_audit", return_value=[]) as run, \
             patch("butler.ops.security_audit.format_audit_report", return_value="x"):
            lifecycle_commands._cmd_doctor(ctx)

        run.assert_called_once()
        # workspace 应该是 Path 对象
        kwargs = run.call_args.kwargs
        assert "workspace" in kwargs
        assert kwargs["workspace"] == Path("/tmp/ws")

    def test_workspace_none_when_no_project(self, owner_env):
        """无 project 时 workspace=None, 不抛异常。"""
        fake_pm = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_pm.get_current.return_value = None
        fake_orch = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_orch.project_manager = fake_pm
        ctx = _make_ctx(orchestrator=fake_orch)

        with patch("butler.ops.security_audit.run_security_audit", return_value=[]) as run, \
             patch("butler.ops.security_audit.format_audit_report", return_value="x"):
            lifecycle_commands._cmd_doctor(ctx)
        assert run.call_args.kwargs.get("workspace") is None

    def test_workspace_resolve_exception_caught(self, owner_env):
        """project_manager.get_current 抛异常 → workspace=None, 不中断。"""
        fake_pm = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_pm.get_current.side_effect = RuntimeError("kaboom")
        fake_orch = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        fake_orch.project_manager = fake_pm
        ctx = _make_ctx(orchestrator=fake_orch)

        with patch("butler.ops.security_audit.run_security_audit", return_value=[]) as run, \
             patch("butler.ops.security_audit.format_audit_report", return_value="x"):
            result = lifecycle_commands._cmd_doctor(ctx)
        assert result == "x"
        assert run.call_args.kwargs.get("workspace") is None


# ── /导出 ──


class TestCmdExport:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/导出", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_export(ctx)
        assert "主公" in result or "Owner" in result

    def test_happy_path_delegates_to_export(self, owner_env):
        """owner 调 /导出 → 委托给 handle_export_session_command, 传 session 上下文。"""
        ctx = _make_ctx(cmd="/导出", arg="last")
        with patch(
            "butler.gateway.commands.export_handlers.handle_export_session_command",
            return_value="(exported)",
        ) as handler:
            result = lifecycle_commands._cmd_export(ctx)
        assert result == "(exported)"
        handler.assert_called_once_with(
            "last",
            platform="wechat",
            external_id="u-owner",
            session_key="test:user1",
        )


# ── /回滚 ──


class TestCmdRevert:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/回滚", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_revert(ctx)
        assert "主公" in result or "Owner" in result

    def test_no_arg_keeps_zero(self, owner_env):
        """arg 为空 → keep=0 → truncate_transcript(... keep_last_lines=None)。"""
        ctx = _make_ctx(cmd="/回滚", arg="")
        with patch("butler.core.transcript_revert.truncate_transcript",
                   return_value={"ok": True, "dropped_lines": 5, "lines_after": 10}) as trunc:
            result = lifecycle_commands._cmd_revert(ctx)
        assert "5 行" in result
        trunc.assert_called_once_with("test:user1", keep_last_lines=None)

    def test_numeric_arg_parses(self, owner_env):
        """arg='20' → keep=20 → truncate_transcript(... keep_last_lines=20)。"""
        ctx = _make_ctx(cmd="/回滚", arg="20")
        with patch("butler.core.transcript_revert.truncate_transcript",
                   return_value={"ok": True, "dropped_lines": 3, "lines_after": 17}) as trunc:
            result = lifecycle_commands._cmd_revert(ctx)
        trunc.assert_called_once_with("test:user1", keep_last_lines=20)

    def test_failure_returns_error(self, owner_env):
        """truncate_transcript 失败 → 返回『回滚失败』+ error 信息。"""
        ctx = _make_ctx(cmd="/回滚", arg="")
        with patch("butler.core.transcript_revert.truncate_transcript",
                   return_value={"ok": False, "error": "transcript locked"}):
            result = lifecycle_commands._cmd_revert(ctx)
        assert "回滚失败" in result
        assert "transcript locked" in result

    def test_skipped_returns_skip_message(self, owner_env):
        """truncate_transcript 跳过 (无需回滚) → 返回 skip 消息。"""
        ctx = _make_ctx(cmd="/回滚", arg="")
        with patch("butler.core.transcript_revert.truncate_transcript",
                   return_value={"ok": True, "skipped": True, "lines_after": 5}):
            result = lifecycle_commands._cmd_revert(ctx)
        assert "无需回滚" in result


# ── /分叉 ──


class TestCmdFork:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/分叉", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_fork(ctx)
        assert "主公" in result or "Owner" in result

    def test_no_arg_defaults_to_user_index_1(self, owner_env):
        """arg 为空 → user_idx=1。"""
        ctx = _make_ctx(cmd="/分叉", arg="")
        with patch("butler.core.transcript_fork.fork_transcript_at_user_message",
                   return_value={"ok": True, "dropped_lines": 0, "lines_after": 10}) as fork:
            result = lifecycle_commands._cmd_fork(ctx)
        fork.assert_called_once_with("test:user1", keep_from_user_index=1)
        assert "fork" in result.lower() or "已从" in result

    def test_numeric_arg_parses(self, owner_env):
        """arg='3' → user_idx=3。"""
        ctx = _make_ctx(cmd="/分叉", arg="3")
        with patch("butler.core.transcript_fork.fork_transcript_at_user_message",
                   return_value={"ok": True, "dropped_lines": 5, "lines_after": 8}) as fork:
            lifecycle_commands._cmd_fork(ctx)
        fork.assert_called_once_with("test:user1", keep_from_user_index=3)

    def test_user_index_not_found_returns_friendly_error(self, owner_env):
        """err='user_index_not_found' → 返回『未找到第 N 条 user 消息』+ 实际计数。"""
        ctx = _make_ctx(cmd="/分叉", arg="5")
        with patch("butler.core.transcript_fork.fork_transcript_at_user_message",
                   return_value={"ok": False, "error": "user_index_not_found",
                                 "user_messages_found": 3}):
            result = lifecycle_commands._cmd_fork(ctx)
        assert "第 5 条" in result
        assert "3 条" in result

    def test_other_error_returns_generic(self, owner_env):
        """其他 error code → 返回『Transcript fork 失败: <err>』。"""
        ctx = _make_ctx(cmd="/分叉", arg="")
        with patch("butler.core.transcript_fork.fork_transcript_at_user_message",
                   return_value={"ok": False, "error": "io_error"}):
            result = lifecycle_commands._cmd_fork(ctx)
        assert "io_error" in result

    def test_skipped_returns_skip_message(self, owner_env):
        """skipped=True → 返回『已在第 N 条 user 消息处』消息。"""
        ctx = _make_ctx(cmd="/分叉", arg="2")
        with patch("butler.core.transcript_fork.fork_transcript_at_user_message",
                   return_value={"ok": True, "skipped": True}):
            result = lifecycle_commands._cmd_fork(ctx)
        assert "第 2 条" in result
        assert "无需 fork" in result or "无需" in result


# ── /记忆提炼 ──


class TestCmdTranscriptMemory:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/记忆提炼", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_transcript_memory(ctx)
        assert "主公" in result or "Owner" in result

    def test_disabled_returns_enable_message(self, owner_env, monkeypatch):
        """transcript_memory_enabled()=False → 返回『未启用』消息。"""
        ctx = _make_ctx(cmd="/记忆提炼", arg="")
        monkeypatch.setenv("BUTLER_TRANSCRIPT_MEMORY", "0")
        # 实际值取决于 transcript_memory_enabled 实现, 这里直接 patch 函数
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=False):
            result = lifecycle_commands._cmd_transcript_memory(ctx)
        assert "未启用" in result

    def test_happy_path_extracts_memory(self, owner_env):
        """enabled + extract ok → 返回『写入 N 条记忆』。"""
        ctx = _make_ctx(cmd="/记忆提炼", arg="my_project")
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=True), \
             patch("butler.memory.transcript_memory_pipeline.extract_memory_from_transcript",
                   return_value={"ok": True, "memory_updates": 7, "errors": []}) as extract:
            result = lifecycle_commands._cmd_transcript_memory(ctx)
        extract.assert_called_once_with("test:user1", project_name="my_project")
        assert "7 条" in result

    def test_failure_returns_error(self, owner_env):
        ctx = _make_ctx(cmd="/记忆提炼", arg="")
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=True), \
             patch("butler.memory.transcript_memory_pipeline.extract_memory_from_transcript",
                   return_value={"ok": False, "error": "transcript empty"}):
            result = lifecycle_commands._cmd_transcript_memory(ctx)
        assert "提炼失败" in result
        assert "transcript empty" in result

    def test_skipped_too_few_messages(self, owner_env):
        """skipped + message_count → 返回『消息不足』消息。"""
        ctx = _make_ctx(cmd="/记忆提炼", arg="")
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=True), \
             patch("butler.memory.transcript_memory_pipeline.extract_memory_from_transcript",
                   return_value={"ok": True, "skipped": True, "message_count": 2}):
            result = lifecycle_commands._cmd_transcript_memory(ctx)
        assert "消息不足" in result or "不足" in result
        assert "2 条" in result

    def test_with_warnings_returns_warning(self, owner_env):
        """errors 列表非空 → 返回『写入 N 条；警告: ...』。"""
        ctx = _make_ctx(cmd="/记忆提炼", arg="")
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=True), \
             patch("butler.memory.transcript_memory_pipeline.extract_memory_from_transcript",
                   return_value={"ok": True, "memory_updates": 3,
                                 "errors": ["warn1", "warn2"]}):
            result = lifecycle_commands._cmd_transcript_memory(ctx)
        assert "3 条" in result
        assert "警告" in result

    def test_arg_empty_falls_back_to_env_default(self, owner_env, monkeypatch):
        """arg 为空 + BUTLER_DEFAULT_PROJECT 也没设 → project_name=""。"""
        ctx = _make_ctx(cmd="/记忆提炼", arg="")
        monkeypatch.delenv("BUTLER_DEFAULT_PROJECT", raising=False)
        with patch("butler.memory.transcript_memory_pipeline.transcript_memory_enabled",
                   return_value=True), \
             patch("butler.memory.transcript_memory_pipeline.extract_memory_from_transcript",
                   return_value={"ok": True, "memory_updates": 0}) as extract:
            lifecycle_commands._cmd_transcript_memory(ctx)
        assert extract.call_args.kwargs["project_name"] == ""


# ── /确认安装 ──


class TestCmdConfirmInstall:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/确认安装", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_confirm_install(ctx)
        assert "主公" in result or "Owner" in result

    def test_happy_path_delegates(self, owner_env):
        """owner 调 /确认安装 → 委托给 handle_confirm_install_command。"""
        ctx = _make_ctx(cmd="/确认安装", arg="skill:foo")
        with patch("butler.gateway.commands.registry_handlers.handle_confirm_install_command",
                   return_value="(confirmed)") as handler:
            result = lifecycle_commands._cmd_confirm_install(ctx)
        assert result == "(confirmed)"
        handler.assert_called_once_with(
            "skill:foo",
            platform="wechat",
            external_id="u-owner",
            session_key="test:user1",
        )


# ── /技能 / /mcp (共享 _cmd_registry) ──


class TestCmdRegistry:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/技能", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_registry(ctx)
        assert "主公" in result or "Owner" in result

    def test_cmd_passed_through(self, owner_env):
        """_cmd_registry 应把 ctx.cmd 传给 handle_registry_command。"""
        for cmd in ("/技能", "/mcp", "/skills"):
            ctx = _make_ctx(cmd=cmd, arg="search foo")
            with patch("butler.gateway.commands.registry_handlers.handle_registry_command",
                       return_value=f"(handled {cmd})") as handler:
                result = lifecycle_commands._cmd_registry(ctx)
            assert result == f"(handled {cmd})"
            handler.assert_called_once_with(
                cmd, "search foo",
                platform="wechat",
                external_id="u-owner",
                session_key="test:user1",
            )


# ── /任务 ──


class TestCmdTasks:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/任务", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_tasks(ctx)
        assert "主公" in result or "Owner" in result

    def test_no_tasks_returns_empty_message(self, owner_env):
        """list_recent_tasks 返回空 → 返回『暂无委派任务记录』。"""
        ctx = _make_ctx(cmd="/任务")
        with patch("butler.runtime.task_store.mark_stale_tasks", return_value=[]), \
             patch("butler.runtime.task_store.list_recent_tasks", return_value=[]), \
             patch("butler.runtime.task_store.count_running_tasks", return_value=0), \
             patch("butler.runtime.task_store.task_stale_minutes", return_value=15):
            result = lifecycle_commands._cmd_tasks(ctx)
        assert "暂无" in result

    def test_with_tasks_renders_table(self, owner_env):
        """有 task rows → 渲染 running count + 每行 status/preview。"""
        ctx = _make_ctx(cmd="/任务")
        rows = [
            {"task_id": "t1", "status": "ok", "success": True, "task_preview": "first"},
            {"task_id": "t2", "status": "failed", "success": False, "task_preview": "second"},
            {"task_id": "t3", "status": "running", "success": None, "task_preview": "third",
             "child_session_key": "child-1", "background": True},
        ]
        with patch("butler.runtime.task_store.mark_stale_tasks", return_value=[]), \
             patch("butler.runtime.task_store.list_recent_tasks", return_value=rows), \
             patch("butler.runtime.task_store.count_running_tasks", return_value=1), \
             patch("butler.runtime.task_store.task_stale_minutes", return_value=15):
            result = lifecycle_commands._cmd_tasks(ctx)
        assert "running: 1" in result
        assert "stale 阈值: 15" in result
        assert "t1" in result
        assert "t2" in result
        assert "t3" in result
        assert "first" in result
        # ✓ / ✗ / … 三个 mark
        assert "✓" in result
        assert "✗" in result
        # child hint
        assert "child-1" in result
        # [后台] tag
        assert "[后台]" in result

    def test_stale_rows_marked_and_warned(self, owner_env):
        """有 stale tasks → 输出『⚠ 僵死任务』 + 行首 ⏱ 标记。"""
        ctx = _make_ctx(cmd="/任务")
        rows = [
            {"task_id": "t1", "status": "running", "success": None, "task_preview": "hung",
             "stale": True},
        ]
        with patch("butler.runtime.task_store.mark_stale_tasks",
                   return_value=[{"task_id": "t1"}]), \
             patch("butler.runtime.task_store.list_recent_tasks", return_value=rows), \
             patch("butler.runtime.task_store.count_running_tasks", return_value=1), \
             patch("butler.runtime.task_store.task_stale_minutes", return_value=10):
            result = lifecycle_commands._cmd_tasks(ctx)
        assert "僵死" in result
        assert "⏱" in result
        assert "[stale]" in result


# ── /工作流 ──


class TestCmdWorkflow:
    def test_owner_gate_rejects_non_owner(self, non_owner_env):
        ctx = _make_ctx(cmd="/工作流", platform="telegram", external_id="x")
        result = lifecycle_commands._cmd_workflow(ctx)
        assert "主公" in result or "Owner" in result

    def test_happy_path_delegates(self, owner_env):
        """owner 调 /工作流 → 委托给 handle_workflow_command, 传 orchestrator/arg/session。"""
        fake_orch = MagicMock()  # noqa: magicmock-no-spec — lifecycle command facade (proj/pm/orch)
        ctx = _make_ctx(cmd="/工作流", arg="list", orchestrator=fake_orch)
        with patch("butler.workflows.commands.handle_workflow_command",
                   return_value="(workflow list)") as handler:
            result = lifecycle_commands._cmd_workflow(ctx)
        assert result == "(workflow list)"
        handler.assert_called_once_with(
            fake_orch, "list",
            session_key="test:user1", platform="wechat",
        )


# ── require_owner helper (Sprint 18-1: 5 文件本地 _require_owner 合并到 command_registry.require_owner) ──


class TestRequireOwnerHelper:
    def test_owner_returns_none(self, owner_env):
        """owner → require_owner 返回 None (gate 通过).

        Sprint 18-1: lifecycle_commands 不再有本地 _require_owner, 改用真源.
        """
        from butler.gateway.command_registry import require_owner
        ctx = _make_ctx()
        result = require_owner(ctx)
        assert result is None

    def test_non_owner_returns_message(self, non_owner_env):
        """非 owner → 返回 owner_required_message() (非 None)。"""
        from butler.gateway.command_registry import require_owner
        ctx = _make_ctx(platform="telegram", external_id="x")
        result = require_owner(ctx)
        assert result is not None
        assert "主公" in result or "Owner" in result


# ── 静态契约: 11 个命令全部注册 ──


class TestStaticContract:
    def test_all_eleven_commands_registered(self):
        """11 个生命周期命令必须全部 register 到 command_registry。"""
        from butler.gateway.command_registry import lookup

        expected = {
            "/doctor", "/导出", "/回滚", "/分叉", "/记忆提炼",
            "/确认安装", "/技能", "/mcp", "/config", "/任务", "/工作流",
        }
        found = {name for name in expected if lookup(name) is not None}
        missing = expected - found
        assert not missing, f"missing registered commands: {missing}"

    def test_all_commands_have_help_text(self):
        """每个命令必须有 help_text (非空)。"""
        from butler.gateway.command_registry import lookup

        names = [
            "/doctor", "/导出", "/回滚", "/分叉", "/记忆提炼",
            "/确认安装", "/技能", "/mcp", "/config", "/任务", "/工作流",
        ]
        for name in names:
            cmd = lookup(name)
            assert cmd is not None, f"{name} should be registered"
            assert cmd.help_text, f"{name} should have non-empty help_text"

    def test_all_commands_have_handler(self):
        """每个命令必须有 handler (非 None, 可调用)。"""
        from butler.gateway.command_registry import lookup

        names = [
            "/doctor", "/导出", "/回滚", "/分叉", "/记忆提炼",
            "/确认安装", "/技能", "/mcp", "/config", "/任务", "/工作流",
        ]
        for name in names:
            cmd = lookup(name)
            assert cmd is not None, f"{name} should be registered"
            assert cmd.handler is not None, f"{name} should have a handler"
            assert callable(cmd.handler), f"{name} handler should be callable"

    def test_aliases_resolve_to_canonical(self):
        """aliases (如 /export, /workflow) 应能解析到 canonical name。"""
        from butler.gateway.command_registry import lookup

        # 每个 alias 应解析到非 None 的 CommandDef
        for alias, canonical in [
            ("/export", "/导出"),
            ("/transcript-revert", "/回滚"),
            ("/fork-transcript", "/分叉"),
            ("/transcript-memory", "/记忆提炼"),
            ("/confirm-install", "/确认安装"),
            ("/skills", "/技能"),
            ("/tasks", "/任务"),
            ("/workflow", "/工作流"),
            ("/配置", "/config"),
        ]:
            resolved = lookup(alias)
            assert resolved is not None, f"alias {alias!r} should resolve"
            assert resolved.name == canonical, (
                f"alias {alias!r} should resolve to {canonical!r}, got {resolved.name!r}"
            )
