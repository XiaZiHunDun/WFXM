"""L1 单元测试：butler.tools.guardrails 工具调用护栏模块。

覆盖范围：
1. ToolCallGuardrailConfig — 默认值、不可变性（frozen）、自定义值
2. classify_tool() — 幂等工具、变更工具、未知工具
3. ToolCallGuardrail — observe()/check() 生命周期、精确失败、
   同一工具失败、无进展、纯幂等循环、reset()、hard_stop、warnings
4. GuardrailDecision — 字段值、默认构造
5. IDEMPOTENT_TOOL_NAMES / MUTATING_TOOL_NAMES — 关键工具分类验证
"""

import pytest

from butler.tools.guardrails import (
    IDEMPOTENT_TOOL_NAMES,
    MUTATING_TOOL_NAMES,
    GuardrailDecision,
    ToolCallGuardrail,
    ToolCallGuardrailConfig,
    classify_tool,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def default_config():
    """返回默认配置。"""
    return ToolCallGuardrailConfig()


@pytest.fixture
def strict_config():
    """返回严格阈值的配置，便于快速触发告警/硬停止。"""
    return ToolCallGuardrailConfig(
        exact_failure_warn_after=2,
        exact_failure_block_after=3,
        same_tool_failure_warn_after=2,
        same_tool_failure_halt_after=4,
        no_progress_warn_after=2,
        no_progress_block_after=3,
    )


@pytest.fixture
def hard_stop_config():
    """启用硬停止的配置。"""
    return ToolCallGuardrailConfig(
        hard_stop_enabled=True,
        warnings_enabled=True,
        exact_failure_warn_after=2,
        exact_failure_block_after=3,
        same_tool_failure_warn_after=2,
        same_tool_failure_halt_after=4,
        no_progress_warn_after=2,
        no_progress_block_after=3,
    )


@pytest.fixture
def guardrail():
    """返回默认护栏实例。"""
    return ToolCallGuardrail()


@pytest.fixture
def strict_guardrail(strict_config):
    """返回严格阈值的护栏实例。"""
    return ToolCallGuardrail(config=strict_config)


# ═══════════════════════════════════════════════════════════════
# 1. ToolCallGuardrailConfig 测试
# ═══════════════════════════════════════════════════════════════


class TestToolCallGuardrailConfig:
    """测试 ToolCallGuardrailConfig 数据类的默认值、不可变性和自定义值。"""

    def test_default_values(self):
        """验证所有默认值符合文档描述。"""
        cfg = ToolCallGuardrailConfig()
        assert cfg.warnings_enabled is True
        assert cfg.hard_stop_enabled is False
        assert cfg.exact_failure_warn_after == 2
        assert cfg.exact_failure_block_after == 5
        assert cfg.same_tool_failure_warn_after == 3
        assert cfg.same_tool_failure_halt_after == 8
        assert cfg.no_progress_warn_after == 2
        assert cfg.no_progress_block_after == 5
        assert cfg.idempotent_tools == IDEMPOTENT_TOOL_NAMES
        assert cfg.mutating_tools == MUTATING_TOOL_NAMES

    def test_frozen_immutability(self):
        """验证 frozen=True 的数据类不可变，赋值应抛异常。"""
        cfg = ToolCallGuardrailConfig()
        with pytest.raises(Exception):
            cfg.warnings_enabled = False  # type: ignore[misc]

    def test_custom_values(self):
        """验证自定义字段可被正确设置。"""
        cfg = ToolCallGuardrailConfig(
            warnings_enabled=False,
            hard_stop_enabled=True,
            exact_failure_warn_after=5,
        )
        assert cfg.warnings_enabled is False
        assert cfg.hard_stop_enabled is True
        assert cfg.exact_failure_warn_after == 5

    def test_custom_idempotent_tools(self):
        """验证可自定义幂等工具集合（覆盖默认值）。"""
        custom = frozenset({"read_file", "grep"})
        cfg = ToolCallGuardrailConfig(idempotent_tools=custom)
        assert cfg.idempotent_tools == custom
        assert "read_file" in cfg.idempotent_tools
        assert "search_codebase" not in cfg.idempotent_tools

    def test_custom_mutating_tools(self):
        """验证可自定义变更工具集合（覆盖默认值）。"""
        custom = frozenset({"write_file", "patch"})
        cfg = ToolCallGuardrailConfig(mutating_tools=custom)
        assert cfg.mutating_tools == custom
        assert "terminal" not in cfg.mutating_tools


# ═══════════════════════════════════════════════════════════════
# 2. classify_tool() 测试
# ═══════════════════════════════════════════════════════════════


class TestClassifyTool:
    """测试 classify_tool() 分类函数。"""

    @pytest.mark.parametrize("tool_name", list(IDEMPOTENT_TOOL_NAMES))
    def test_idempotent_tools(self, tool_name):
        """验证集合中所有幂等工具被分类为 'idempotent'。"""
        assert classify_tool(tool_name) == "idempotent"

    @pytest.mark.parametrize("tool_name", list(MUTATING_TOOL_NAMES))
    def test_mutating_tools(self, tool_name):
        """验证集合中所有变更工具被分类为 'mutating'。"""
        assert classify_tool(tool_name) == "mutating"

    def test_unknown_tool_nonexistent(self):
        """验证不存在的工具名返回 'unknown'。"""
        assert classify_tool("nonexistent_tool_xyz") == "unknown"

    def test_unknown_tool_empty_string(self):
        """验证空字符串工具名返回 'unknown'。"""
        assert classify_tool("") == "unknown"

    def test_unknown_tool_arbitrary_string(self):
        """验证任意未注册的工具名返回 'unknown'。"""
        assert classify_tool("foobar_baz_tool") == "unknown"

    def test_key_idempotent_tools(self):
        """验证关键幂等工具（开发者最常用）分类正确。"""
        assert classify_tool("read_file") == "idempotent"
        assert classify_tool("search_files") == "idempotent"
        assert classify_tool("search_codebase") == "idempotent"
        assert classify_tool("grep") == "idempotent"
        assert classify_tool("glob") == "idempotent"
        assert classify_tool("list_directory") == "idempotent"
        assert classify_tool("web_search") == "idempotent"
        assert classify_tool("web_fetch") == "idempotent"
        assert classify_tool("knowledge_search") == "idempotent"

    def test_key_mutating_tools(self):
        """验证关键变更工具（开发者最常用）分类正确。"""
        assert classify_tool("write_file") == "mutating"
        assert classify_tool("patch") == "mutating"
        assert classify_tool("delete_file") == "mutating"
        assert classify_tool("create_file") == "mutating"
        assert classify_tool("terminal") == "mutating"
        assert classify_tool("execute_code") == "mutating"
        assert classify_tool("git_commit") == "mutating"
        assert classify_tool("move_file") == "mutating"


# ═══════════════════════════════════════════════════════════════
# 3. GuardrailDecision 测试
# ═══════════════════════════════════════════════════════════════


class TestGuardrailDecision:
    """测试 GuardrailDecision 数据类的字段和默认值。"""

    def test_default_construction(self):
        """验证默认构造值。"""
        decision = GuardrailDecision()
        assert decision.should_warn is False
        assert decision.should_hard_stop is False
        assert decision.warning_message is None
        assert decision.halt_message is None
        assert decision.reason == "ok"

    def test_custom_warning_decision(self):
        """验证告警决策的自定义字段。"""
        decision = GuardrailDecision(
            should_warn=True,
            should_hard_stop=False,
            warning_message="test warning message",
            halt_message=None,
            reason="exact_failure_warn",
        )
        assert decision.should_warn is True
        assert decision.should_hard_stop is False
        assert decision.warning_message == "test warning message"
        assert decision.halt_message is None
        assert decision.reason == "exact_failure_warn"

    def test_custom_hard_stop_decision(self):
        """验证硬停止决策的自定义字段。"""
        decision = GuardrailDecision(
            should_warn=False,
            should_hard_stop=True,
            warning_message=None,
            halt_message="halt message content",
            reason="exact_failure_block",
        )
        assert decision.should_warn is False
        assert decision.should_hard_stop is True
        assert decision.warning_message is None
        assert decision.halt_message == "halt message content"
        assert decision.reason == "exact_failure_block"

    def test_decision_equality(self):
        """验证同字段值的决策相等。"""
        d1 = GuardrailDecision(should_warn=True, reason="ok")
        d2 = GuardrailDecision(should_warn=True, reason="ok")
        assert d1 == d2


# ═══════════════════════════════════════════════════════════════
# 4. ToolCallGuardrail 测试
# ═══════════════════════════════════════════════════════════════


class TestToolCallGuardrail:
    """测试 ToolCallGuardrail 的 observe/check 生命周期及各类循环检测。"""

    # ── 基础生命周期 ──

    def test_empty_history_returns_ok(self, guardrail):
        """空历史 → check 返回 ok，无告警无硬停止。"""
        decision = guardrail.check()
        assert decision.reason == "ok"
        assert decision.should_warn is False
        assert decision.should_hard_stop is False

    def test_successful_calls_no_warning(self, guardrail):
        """只有成功调用且有幂等读穿插 → 无告警。"""
        guardrail.observe("read_file", True, "file content")
        guardrail.observe("write_file", True, "file written")
        guardrail.observe("read_file", True, "verify")
        guardrail.observe("patch", True, "patched")
        decision = guardrail.check()
        assert decision.reason == "ok"

    def test_observe_check_lifecycle(self, guardrail):
        """基本 observe + check 生命周期，逐步验证。"""
        guardrail.observe("read_file", True, "ok")
        decision = guardrail.check()
        assert decision.reason == "ok"

    def test_history_empty_initially(self, guardrail):
        """初始历史为空元组。"""
        assert guardrail.history == ()

    def test_history_property_returns_tuple(self, guardrail):
        """history 属性返回不可变元组，元素为 _Observation。"""
        guardrail.observe("read_file", True, "ok")
        guardrail.observe("write_file", False, "error")
        history = guardrail.history
        assert isinstance(history, tuple)
        assert len(history) == 2
        assert history[0].tool_name == "read_file"
        assert history[0].result_ok is True
        assert history[0].result_summary == "ok"
        assert history[1].tool_name == "write_file"
        assert history[1].result_ok is False
        assert history[1].result_summary == "error"

    def test_config_property(self, guardrail, default_config):
        """config 属性返回与默认配置相等的对象。"""
        assert guardrail.config == default_config
        assert guardrail.config.warnings_enabled is True

    def test_none_summary_treated_as_empty(self, guardrail):
        """result_summary=None 被替换为空字符串。"""
        guardrail.observe("read_file", False)
        history = guardrail.history
        assert history[0].result_summary == ""

    def test_empty_string_summary(self, guardrail):
        """空字符串摘要正常存储。"""
        guardrail.observe("read_file", False, "")
        history = guardrail.history
        assert history[0].result_summary == ""

    def test_max_history_eviction(self):
        """超过 max_history 的记录被挤出（FIFO）。"""
        gr = ToolCallGuardrail(max_history=3)
        for i in range(5):
            gr.observe("read_file", True, f"call_{i}")
        assert len(gr.history) == 3
        assert gr.history[0].result_summary == "call_2"
        assert gr.history[2].result_summary == "call_4"

    # ── 精确失败检测 ──

    def test_exact_failure_warning(self, strict_guardrail):
        """相同工具 + 相同摘要 → 触发精确失败告警。"""
        for _ in range(2):
            strict_guardrail.observe("read_file", False, "file not found")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.should_hard_stop is False
        assert decision.reason == "exact_failure_warn"
        assert "read_file" in decision.warning_message
        assert "file not found" in decision.warning_message

    def test_exact_failure_block_with_hard_stop(self, hard_stop_config):
        """相同工具 + 相同摘要 + 硬停止 → 触发硬停止。"""
        gr = ToolCallGuardrail(config=hard_stop_config)
        for _ in range(3):
            gr.observe("terminal", False, "exit code 1")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.should_warn is False
        assert decision.reason == "exact_failure_block"
        assert "terminal" in decision.halt_message
        assert "exit code 1" in decision.halt_message

    def test_exact_failure_not_triggered_by_different_summaries(self, strict_guardrail):
        """相同工具 + 不同摘要 → 不触发精确失败（走同一工具失败分支）。"""
        strict_guardrail.observe("read_file", False, "error A")
        strict_guardrail.observe("read_file", False, "error B")
        decision = strict_guardrail.check()
        assert decision.reason != "exact_failure_warn"
        assert decision.reason != "exact_failure_block"

    def test_exact_failure_counts_all_failures_globally(self, strict_guardrail):
        """精确失败检测全局累计所有失败，成功调用不中断计数。"""
        strict_guardrail.observe("read_file", False, "error")
        strict_guardrail.observe("read_file", True, "ok")
        strict_guardrail.observe("read_file", False, "error")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "exact_failure_warn"

    def test_exact_failure_block_requires_hard_stop(self, hard_stop_config):
        """精确失败硬停止仅在 hard_stop_enabled=True 时触发。"""
        gr = ToolCallGuardrail(config=hard_stop_config)
        for _ in range(3):
            gr.observe("patch", False, "syntax error")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.reason == "exact_failure_block"

    # ── 同一工具失败检测 ──

    def test_same_tool_failure_warning(self, strict_guardrail):
        """相同工具 + 不同摘要 → 触发同一工具失败告警。"""
        strict_guardrail.observe("write_file", False, "disk full")
        strict_guardrail.observe("write_file", False, "permission denied")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.should_hard_stop is False
        assert decision.reason == "same_tool_failure_warn"
        assert "write_file" in decision.warning_message

    def test_same_tool_failure_halt_with_hard_stop(self, hard_stop_config):
        """相同工具多次失败 + 硬停止 → 触发硬停止。"""
        gr = ToolCallGuardrail(config=hard_stop_config)
        for i in range(4):
            gr.observe("patch", False, f"error {i}")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.reason == "same_tool_failure_halt"
        assert "patch" in decision.halt_message

    def test_same_tool_failure_counts_all_failures_globally(self, strict_guardrail):
        """同一工具失败检测全局累计所有失败，成功调用不中断计数。"""
        strict_guardrail.observe("read_file", False, "error A")
        strict_guardrail.observe("read_file", True, "ok")
        strict_guardrail.observe("read_file", False, "error B")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "same_tool_failure_warn"

    def test_same_tool_failure_countes_across_different_summaries(self, strict_guardrail):
        """同一工具不同错误摘要累加计数。"""
        strict_guardrail.observe("search_codebase", False, "index error")
        strict_guardrail.observe("search_codebase", False, "timeout")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "same_tool_failure_warn"

    # ── 无进展检测 ──

    def test_no_progress_warning(self, strict_guardrail):
        """连续变更调用 + 无成功读取 → 触发无进展告警。"""
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "no_progress_warn"

    def test_no_progress_block_with_hard_stop(self, hard_stop_config):
        """连续变更调用 + 硬停止 → 触发无进展硬停止。"""
        gr = ToolCallGuardrail(config=hard_stop_config)
        for _ in range(3):
            gr.observe("patch", True, "patched")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.reason == "no_progress_block"

    def test_no_progress_resets_after_idempotent_success(self, strict_guardrail):
        """成功的幂等调用重置无进展检测。"""
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    def test_no_progress_breaks_after_idempotent_failure(self, strict_guardrail):
        """失败的幂等工具打断无进展链。"""
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("search_codebase", False, "index error")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    def test_no_progress_breaks_after_unknown_tool(self, strict_guardrail):
        """未知工具打断无进展链。"""
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("unknown_tool_xyz", True, "result")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    def test_no_progress_requires_consecutive_mutating(self, strict_guardrail):
        """只有连续的变更调用才触发。"""
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("patch", True, "patched")
        strict_guardrail.observe("grep", True, "results")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    # ── 纯幂等循环检测 ──

    def test_idempotent_only_warning(self, strict_guardrail):
        """连续幂等调用 + 无变更 → 触发纯幂等告警。"""
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("search_codebase", True, "results")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "idempotent_only_warn"
        assert "read-only" in decision.warning_message

    def test_idempotent_only_resets_after_mutating(self, strict_guardrail):
        """变更调用重置纯幂等循环检测。"""
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("read_file", True, "content")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    def test_idempotent_only_counts_failed_idempotent(self, strict_guardrail):
        """失败的幂等工具也计入纯幂等循环。"""
        strict_guardrail.observe("read_file", False, "not found")
        strict_guardrail.observe("grep", True, "results")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason == "idempotent_only_warn"

    def test_idempotent_only_breaks_on_unknown(self, strict_guardrail):
        """未知工具打断纯幂等循环链。"""
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("unknown_tool_xyz", True, "result")
        strict_guardrail.observe("search_codebase", True, "results")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    def test_idempotent_only_requires_no_mutating_in_between(self, strict_guardrail):
        """幂等→变更→幂等 不触发纯幂等检测。"""
        strict_guardrail.observe("read_file", True, "c1")
        strict_guardrail.observe("search_codebase", True, "r1")
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("grep", True, "results")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    # ── reset() 测试 ──

    def test_reset_clears_all_state(self, strict_guardrail):
        """reset() 清除所有历史记录，check 返回 ok。"""
        strict_guardrail.observe("read_file", False, "error")
        strict_guardrail.observe("write_file", False, "error")
        assert len(strict_guardrail.history) == 2
        strict_guardrail.reset()
        decision = strict_guardrail.check()
        assert decision.reason == "ok"
        assert len(strict_guardrail.history) == 0

    def test_reset_idempotent_multiple_calls(self, strict_guardrail):
        """reset() 多次调用安全幂等。"""
        strict_guardrail.observe("read_file", False, "error")
        strict_guardrail.reset()
        strict_guardrail.reset()
        strict_guardrail.reset()
        decision = strict_guardrail.check()
        assert decision.reason == "ok"
        assert len(strict_guardrail.history) == 0

    def test_reset_allows_fresh_start(self, strict_guardrail):
        """reset() 后可以重新开始观察。"""
        for _ in range(3):
            strict_guardrail.observe("terminal", False, "exit 1")
        strict_guardrail.reset()
        strict_guardrail.observe("read_file", True, "fresh start")
        decision = strict_guardrail.check()
        assert decision.reason == "ok"

    # ── hard_stop_enabled 行为 ──

    def test_hard_stop_disabled_no_hard_stop(self, strict_guardrail):
        """hard_stop_enabled=False → 任何情况下不触发硬停止。"""
        for _ in range(10):
            strict_guardrail.observe("terminal", False, "exit 1")
        decision = strict_guardrail.check()
        assert decision.should_hard_stop is False

    def test_hard_stop_enabled_blocks(self, hard_stop_config):
        """hard_stop_enabled=True → 达到阈值后触发硬停止。"""
        gr = ToolCallGuardrail(config=hard_stop_config)
        for _ in range(3):
            gr.observe("terminal", False, "exit 1")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.reason == "exact_failure_block"

    def test_hard_stop_disabled_still_allows_warnings(self, strict_guardrail):
        """hard_stop 禁用但告警启用 → 仍可触发告警。"""
        for _ in range(2):
            strict_guardrail.observe("read_file", False, "same error")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.should_hard_stop is False

    # ── warnings_enabled 切换 ──

    def test_warnings_disabled_no_warnings(self):
        """warnings_enabled=False → 不触发任何告警。"""
        cfg = ToolCallGuardrailConfig(
            warnings_enabled=False,
            hard_stop_enabled=False,
            exact_failure_warn_after=2,
            same_tool_failure_warn_after=2,
            no_progress_warn_after=2,
        )
        gr = ToolCallGuardrail(config=cfg)
        for _ in range(5):
            gr.observe("read_file", False, "error")
        decision = gr.check()
        assert decision.should_warn is False
        assert decision.reason == "ok"

    def test_warnings_enabled_by_default(self, guardrail):
        """默认配置启用告警。"""
        assert guardrail.config.warnings_enabled is True

    def test_warnings_disabled_hard_stop_still_works(self):
        """warnings 禁用但 hard_stop 启用 → 硬停止仍可触发。"""
        cfg = ToolCallGuardrailConfig(
            warnings_enabled=False,
            hard_stop_enabled=True,
            exact_failure_warn_after=2,
            exact_failure_block_after=3,
        )
        gr = ToolCallGuardrail(config=cfg)
        for _ in range(3):
            gr.observe("terminal", False, "exit 1")
        decision = gr.check()
        assert decision.should_hard_stop is True
        assert decision.should_warn is False

    # ── 优先级顺序 ──

    def test_exact_failure_takes_priority_over_same_tool(self, strict_guardrail):
        """精确失败优先级高于同一工具失败。"""
        for _ in range(2):
            strict_guardrail.observe("read_file", False, "same error")
        strict_guardrail.observe("write_file", False, "write error")
        decision = strict_guardrail.check()
        assert decision.reason == "exact_failure_warn"

    def test_same_tool_failure_takes_priority_over_no_progress(self, strict_guardrail):
        """同一工具失败优先级高于无进展检测。"""
        strict_guardrail.observe("write_file", False, "err1")
        strict_guardrail.observe("write_file", False, "err2")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.reason == "same_tool_failure_warn"

    def test_no_progress_takes_priority_over_idempotent_only(self, strict_guardrail):
        """无进展检测优先级高于纯幂等循环。"""
        strict_guardrail.observe("read_file", True, "content")
        strict_guardrail.observe("write_file", True, "written")
        strict_guardrail.observe("patch", True, "patched")
        decision = strict_guardrail.check()
        assert decision.reason == "no_progress_warn"

    # ── 多工具混合场景 ──

    def test_mixed_idempotent_and_mutating_no_loop(self, guardrail):
        """交替幂等和变更调用不触发循环检测。"""
        actions = [
            ("read_file", True, "content"),
            ("write_file", True, "written"),
            ("read_file", True, "content2"),
            ("patch", True, "patched"),
            ("grep", True, "results"),
        ]
        for tool, ok, summary in actions:
            guardrail.observe(tool, ok, summary)
        decision = guardrail.check()
        assert decision.reason == "ok"

    def test_multiple_tools_no_confusion(self, strict_guardrail):
        """不同工具交替失败，各计数独立。"""
        strict_guardrail.observe("read_file", False, "err")
        strict_guardrail.observe("write_file", False, "err")
        strict_guardrail.observe("read_file", False, "err")
        strict_guardrail.observe("write_file", False, "err")
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert decision.reason in ("exact_failure_warn", "same_tool_failure_warn")

    # ── 摘要截断 ──

    def test_warning_message_truncates_long_summary(self, strict_guardrail):
        """长摘要在告警消息中被截断至 200 字符。"""
        long_summary = "x" * 300
        for _ in range(2):
            strict_guardrail.observe("read_file", False, long_summary)
        decision = strict_guardrail.check()
        assert decision.should_warn is True
        assert "xxxxx" in decision.warning_message


# ═══════════════════════════════════════════════════════════════
# 5. 工具分类集合验证
# ═══════════════════════════════════════════════════════════════


class TestToolClassificationSets:
    """验证 IDEMPOTENT_TOOL_NAMES / MUTATING_TOOL_NAMES 的完整性和一致性。"""

    def test_both_sets_not_empty(self):
        """两个集合均非空。"""
        assert len(IDEMPOTENT_TOOL_NAMES) > 0, "幂等工具集合不应为空"
        assert len(MUTATING_TOOL_NAMES) > 0, "变更工具集合不应为空"

    def test_no_overlap_between_sets(self):
        """两个集合不应有交集（同一工具不能既是幂等又是变更）。"""
        overlap = IDEMPOTENT_TOOL_NAMES & MUTATING_TOOL_NAMES
        assert len(overlap) == 0, f"存在重叠工具: {overlap}"

    @pytest.mark.parametrize("tool_name", [
        "read_file", "search_files", "search_codebase", "grep",
        "glob", "list_directory", "web_search", "web_fetch",
        "browser_snapshot", "browser_navigate",
        "browser_get_console_messages", "browser_network_requests",
        "get_tool_info", "get_domains_for_tool", "get_all_tools",
        "get_recommended_tools", "knowledge_search", "memory_query",
        "data_query", "project_todos", "session_todos",
        "memo", "habits", "reminder",
        "skill_view", "skills_list",
        "multimodal_analyze", "multimodal_describe",
        "download_tools", "experience_selector",
    ])
    def test_idempotent_key_tools_in_set(self, tool_name):
        """验证关键幂等工具确实在幂等集合中，且分类正确。"""
        assert tool_name in IDEMPOTENT_TOOL_NAMES
        assert classify_tool(tool_name) == "idempotent"

    @pytest.mark.parametrize("tool_name", [
        "terminal", "terminal_run", "terminal_sandbox",
        "write_file", "patch", "delete_file", "create_file",
        "move_file", "rename_file",
        "browser_click", "browser_type", "browser_press_key",
        "browser_upload", "browser_form_submit", "browser_screenshot",
        "execute_code", "run_workflow",
        "delegate_task", "delegate_run",
        "git_commit", "git_push", "git_checkout",
        "git_merge", "git_rebase", "git_tag",
        "create_branch", "create_tag",
        "add_experience", "update_experience", "delete_experience",
        "record_habit", "project_todos_update", "session_todos_update",
        "expense_log", "add_memo", "update_memo", "delete_memo",
        "network_route_verify", "add_knowledge", "consistency_summary",
    ])
    def test_mutating_key_tools_in_set(self, tool_name):
        """验证关键变更工具确实在变更集合中，且分类正确。"""
        assert tool_name in MUTATING_TOOL_NAMES
        assert classify_tool(tool_name) == "mutating"

    def test_all_idempotent_tools_classified_as_idempotent(self):
        """幂等集合中每个工具都应被 classify_tool 识别为 idempotent。"""
        for tool in IDEMPOTENT_TOOL_NAMES:
            assert classify_tool(tool) == "idempotent", (
                f"{tool} 应被分类为 idempotent"
            )

    def test_all_mutating_tools_classified_as_mutating(self):
        """变更集合中每个工具都应被 classify_tool 识别为 mutating。"""
        for tool in MUTATING_TOOL_NAMES:
            assert classify_tool(tool) == "mutating", (
                f"{tool} 应被分类为 mutating"
            )

    def test_total_counts_match(self):
        """集合大小与预期一致（防止意外删除或添加）。"""
        # 当前版本：30 个幂等工具 + 40 个变更工具
        assert len(IDEMPOTENT_TOOL_NAMES) == 30
        assert len(MUTATING_TOOL_NAMES) == 40