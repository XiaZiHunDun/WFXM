"""Tests for butler.gateway.command_registry."""

import pytest

from butler.gateway.command_registry import (
    CommandDef,
    all_commands,
    categories,
    format_registry_help,
    lookup,
    register,
)


# Sprint 11 TST-10-5: 这些命令还有 inline handler 在 message_handler.py, 还未迁移到 registry。
# 迁移一个就从这个 set 移除一个。 当 set 为空时, 全部命令走 registry dispatch。
# Sprint 11 第一批迁移: /会话 /评价 /诊断 — 已在 butler/gateway/commands/info_commands.py 注册。
# Sprint 16 迁移: /记忆图谱 /记忆待审 /拒绝记忆 /批准记忆 — 已在 butler/gateway/commands/memory_commands.py 注册。
_KNOWN_INLINE_COMMANDS: frozenset[str] = frozenset({
    "/项目",
    "/项目 体检",
    "/项目 新建",
    "/切换",
    "/模型",
    "/状态",
    "/新对话",
    "/git",
    "/测试",
    "/构建",
    "/开发状态",
    "/开发验收",
    "/定时",
    "/始终允许",
    "/批准一次",
    "/批准执行",
    "/批准模式",
    "/继续",
    "/权限",
    "/urgent",
    "/later",
    "/项目概况",
    "/停止",
})


# 测试 artifact — 由 test_register_custom_command 注册, 隔离在另一个 set 防止污染迁移测试。
_TEST_ARTIFACT_COMMANDS: frozenset[str] = frozenset({
    "/test_custom_xyz",
})


class TestCommandRegistry:
    def test_lookup_existing(self):
        cmd = lookup("/项目")
        assert cmd is not None
        assert cmd.name == "/项目"

    def test_lookup_alias(self):
        cmd = lookup("/projects")
        assert cmd is not None
        assert cmd.name == "/项目"

    def test_lookup_unknown(self):
        assert lookup("/nonexistent") is None

    def test_all_commands_returns_list(self):
        cmds = all_commands()
        assert len(cmds) > 30

    def test_all_commands_visibility_filter(self):
        public_cmds = all_commands(visibility="public")
        admin_cmds = all_commands(visibility="admin")
        assert len(public_cmds) > len(admin_cmds)

    def test_categories_non_empty(self):
        cats = categories()
        assert len(cats) > 0
        for cat, cmds in cats.items():
            assert len(cmds) > 0

    def test_format_registry_help_overview(self):
        result = format_registry_help()
        assert "命令" in result or "帮助" in result

    def test_format_registry_help_specific_command(self):
        result = format_registry_help("诊断")
        assert "诊断" in result

    def test_register_custom_command(self):
        cmd = CommandDef("/test_custom_xyz", (), "测试", "自定义测试命令")
        register(cmd)
        assert lookup("/test_custom_xyz") is not None


# ── Sprint 11 TST-10-5: 28 CommandDef 缺 handler 迁移跟踪 ──


class TestInlineCommandMigration:
    """跟踪 inline handler 迁移进度的测试。

    每个被迁移的命令:
      - 从 ``_KNOWN_INLINE_COMMANDS`` 移除
      - 加一个 ``CommandDef(... handler=_cmd_xxx)`` 到对应 commands/*.py
      - message_handler.py 的 if/elif 块删除

    当 ``_KNOWN_INLINE_COMMANDS`` 为空时, 所有命令都走 registry dispatch。
    """

    @pytest.fixture
    def ensure_handlers_registered(self):
        # 触发 commands/* 子模块的 register() 调用
        import butler.gateway.commands  # noqa: F401
        return None

    def test_no_unexpected_commands_need_handler(
        self, ensure_handlers_registered,
    ):
        """每个注册命令要么有 handler, 要么在 _KNOWN_INLINE_COMMANDS 白名单里。

        防止: 有人新加 CommandDef 但忘了给 handler, 又忘了加白名单 → 默默走 inline。
        """
        missing = []
        for c in all_commands():
            if (
                c.handler is None
                and c.name not in _KNOWN_INLINE_COMMANDS
                and c.name not in _TEST_ARTIFACT_COMMANDS
            ):
                missing.append(c.name)
        assert missing == [], (
            f"以下命令既无 handler 也未在迁移白名单中, 会走未定义路径: {missing}"
        )

    def test_known_inline_set_is_finite(self, ensure_handlers_registered):
        """白名单不应无限增长 — 每次 sprint 应该至少迁移一个。"""
        # Sprint 11 baseline: 30 inline; 首期迁移 3 个 (/会话 /评价 /诊断) → 27
        # Sprint 12+: 每次合并 _cmd_xxx 注册后, 集合应减小
        assert len(_KNOWN_INLINE_COMMANDS) <= 27, (
            f"_KNOWN_INLINE_COMMANDS 增长到 {len(_KNOWN_INLINE_COMMANDS)}, "
            "应有持续迁移, 而不是堆积"
        )

    def test_inline_command_still_dispatches(self, ensure_handlers_registered):
        """inline 命令在迁移前必须可 dispatch (防止 audit 报告的 0 e2e 退化)。"""
        # 真实 dispatch 验证在 test_gateway_handler.TestEveryRegisteredCommandDispatches
        # 这里只验证白名单中的每个名字都能被 lookup 到
        for name in _KNOWN_INLINE_COMMANDS:
            assert lookup(name) is not None, (
                f"inline 命令 {name!r} 在 registry 中查不到 — 迁移前已损坏"
            )
