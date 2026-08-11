"""butler.tools.budget_config 模块的 pytest 测试套件。

覆盖范围:
1. BudgetConfig: 构造、frozen 不可变性、字段默认值
2. resolve_threshold(): 置顶工具(inf)、tool_overrides 优先级、回退到默认值
3. scale_to_context(): 比例缩放、最小下限
4. with_overrides(): 返回新实例、正确合并
5. DEFAULT_BUDGET: 是 BudgetConfig 实例
6. TurnBudgetTracker: record_result/remaining、exceeded 检测、多工具累积、reset、负数截断
7. PINNED_THRESHOLDS: read_file/glob/grep 返回 inf
"""

import math
from typing import Dict

import pytest

from butler.tools.budget_config import (
    DEFAULT_BUDGET,
    DEFAULT_PREVIEW_SIZE_CHARS,
    DEFAULT_RESULT_SIZE_CHARS,
    DEFAULT_TURN_BUDGET_CHARS,
    PINNED_THRESHOLDS,
    BudgetConfig,
    TurnBudgetTracker,
    _MIN_RESULT_SIZE_CHARS,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def config() -> BudgetConfig:
    """返回一个使用默认值的 BudgetConfig 实例。"""
    return BudgetConfig()


@pytest.fixture
def custom_config() -> BudgetConfig:
    """返回一个带自定义阈值和 tool_overrides 的 BudgetConfig。"""
    return BudgetConfig(
        default_result_size=50_000,
        turn_budget=100_000,
        preview_size=800,
        tool_overrides={"bash": 10_000, "my_tool": 42},
    )


@pytest.fixture
def tracker(config) -> TurnBudgetTracker:
    """返回一个使用默认预算的 TurnBudgetTracker。"""
    return TurnBudgetTracker(budget=config)


@pytest.fixture
def tight_tracker() -> TurnBudgetTracker:
    """返回一个使用 1000 字符紧凑预算的 TurnBudgetTracker。"""
    return TurnBudgetTracker(budget=BudgetConfig(turn_budget=1_000))


# ── 1. BudgetConfig: 构造 / 默认值 / 不可变性 ────────────────────


class TestBudgetConfigConstruction:
    """BudgetConfig 的基本构造和 frozen 行为测试。"""

    def test_default_construction(self) -> None:
        """无参构造时应填入正确的默认值。"""
        cfg = BudgetConfig()
        assert cfg.default_result_size == DEFAULT_RESULT_SIZE_CHARS
        assert cfg.turn_budget == DEFAULT_TURN_BUDGET_CHARS
        assert cfg.preview_size == DEFAULT_PREVIEW_SIZE_CHARS
        assert cfg.tool_overrides == {}

    def test_custom_construction(self, custom_config: BudgetConfig) -> None:
        """显式传参构造时字段值应与传入一致。"""
        assert custom_config.default_result_size == 50_000
        assert custom_config.turn_budget == 100_000
        assert custom_config.preview_size == 800
        assert custom_config.tool_overrides == {"bash": 10_000, "my_tool": 42}

    def test_frozen_immutability(self, config: BudgetConfig) -> None:
        """frozen dataclass 不允许修改字段。"""
        with pytest.raises(Exception):
            config.default_result_size = 999  # type: ignore[misc]

    def test_tool_overrides_independence(self) -> None:
        """两个 BudgetConfig 实例的 tool_overrides 字典应相互独立。"""
        cfg1 = BudgetConfig(tool_overrides={"a": 1})
        cfg2 = BudgetConfig(tool_overrides={"a": 1})
        # 修改 cfg1 的字典不应影响 cfg2
        object.__setattr__(cfg1, "tool_overrides", {"b": 2})
        assert cfg2.tool_overrides == {"a": 1}

    def test_tool_overrides_empty_default(self) -> None:
        """默认构造的 tool_overrides 应为空字典。"""
        cfg = BudgetConfig()
        assert cfg.tool_overrides == {}


# ── 2. resolve_threshold 优先级 ──────────────────────────────────


class TestResolveThreshold:
    """resolve_threshold 方法的优先级解析测试。

    优先级 (高→低):
    1. PINNED_THRESHOLDS
    2. tool_overrides
    3. registry 映射
    4. default_result_size
    """

    # —— 置顶工具 ——

    @pytest.mark.parametrize("tool_name", list(PINNED_THRESHOLDS.keys()))
    def test_pinned_tools_return_inf(self, config: BudgetConfig, tool_name: str) -> None:
        """所有 PINNED_THRESHOLDS 中的工具应返回 math.inf。"""
        result = config.resolve_threshold(tool_name)
        assert math.isinf(result), f"{tool_name} 应返回 inf, 实际: {result}"

    def test_pinned_tool_override_ignored(self, config: BudgetConfig) -> None:
        """tool_overrides 中的置顶工具条目应被忽略, 仍返回 inf。"""
        attacked = config.with_overrides({"read_file": 1000})
        assert math.isinf(attacked.resolve_threshold("read_file"))

    def test_pinned_tool_registry_ignored(self, config: BudgetConfig) -> None:
        """registry 中的置顶工具条目应被忽略, 仍返回 inf。"""
        registry = {"read_file": 500}
        assert math.isinf(config.resolve_threshold("read_file", registry))

    def test_pinned_tool_override_and_registry_ignored(self, config: BudgetConfig) -> None:
        """同时有 override 和 registry 的置顶工具仍返回 inf。"""
        attacked = config.with_overrides({"read_file": 1000})
        registry = {"read_file": 500}
        assert math.isinf(attacked.resolve_threshold("read_file", registry))

    # —— tool_overrides 优先级 ——

    def test_override_beats_registry(self, config: BudgetConfig) -> None:
        """tool_overrides 中的值应优先于 registry。"""
        cfg = config.with_overrides({"my_tool": 42})
        registry = {"my_tool": 9999, "another": 8888}
        assert cfg.resolve_threshold("my_tool", registry) == 42

    def test_override_beats_default(self, config: BudgetConfig) -> None:
        """tool_overrides 中的值应优先于 default_result_size。"""
        cfg = config.with_overrides({"custom": 777})
        assert cfg.resolve_threshold("custom") == 777

    def test_override_returns_float(self, config: BudgetConfig) -> None:
        """即使 override 是 int, 返回值也应为 float 类型。"""
        cfg = config.with_overrides({"tool": 100})
        result = cfg.resolve_threshold("tool")
        assert isinstance(result, float)
        assert result == 100.0

    # —— registry 回退 ——

    def test_registry_used_when_no_override(self, config: BudgetConfig) -> None:
        """无 override 时应从 registry 取值。"""
        registry = {"another_tool": 8888}
        assert config.resolve_threshold("another_tool", registry) == 8888

    def test_registry_skipped_for_pinned_despite_entry(self, config: BudgetConfig) -> None:
        """即使 registry 中有置顶工具的条目, 仍应返回 inf。"""
        registry = {"glob": 500}
        assert math.isinf(config.resolve_threshold("glob", registry))

    # —— 默认回退 ——

    def test_fallback_to_default(self, config: BudgetConfig) -> None:
        """无 override 且无 registry 时应回退到 default_result_size。"""
        result = config.resolve_threshold("unknown_tool")
        assert result == float(DEFAULT_RESULT_SIZE_CHARS)

    def test_fallback_to_default_when_registry_misses(self, config: BudgetConfig) -> None:
        """registry 存在但不包含目标工具时应回退到 default。"""
        registry: Dict[str, int] = {"other": 100}
        result = config.resolve_threshold("unknown_tool", registry)
        assert result == float(DEFAULT_RESULT_SIZE_CHARS)

    def test_no_registry_provided(self, config: BudgetConfig) -> None:
        """registry 为 None 时应正常回退到 default。"""
        result = config.resolve_threshold("any_tool", registry=None)
        assert result == float(DEFAULT_RESULT_SIZE_CHARS)

    def test_return_type_is_float(self, config: BudgetConfig) -> None:
        """非置顶工具的返回类型也应为 float。"""
        result = config.resolve_threshold("bash")
        assert isinstance(result, float)


# ── 3. scale_to_context 比例缩放 ─────────────────────────────────


class TestScaleToContext:
    """scale_to_context 方法的缩放逻辑测试。"""

    def test_small_context_floor(self, config: BudgetConfig) -> None:
        """极小上下文窗口不应低于 MIN_RESULT_SIZE_CHARS 下限。"""
        scaled = config.scale_to_context(4_000)
        assert scaled.default_result_size >= _MIN_RESULT_SIZE_CHARS
        assert scaled.turn_budget >= _MIN_RESULT_SIZE_CHARS * 2

    def test_large_context_scales_up(self, config: BudgetConfig) -> None:
        """大上下文窗口的缩放值应大于默认值。"""
        scaled = config.scale_to_context(200_000)
        assert scaled.default_result_size > config.default_result_size
        assert scaled.turn_budget > config.turn_budget

    def test_preview_size_preserved(self, config: BudgetConfig) -> None:
        """缩放不应改变 preview_size。"""
        scaled = config.scale_to_context(100_000)
        assert scaled.preview_size == config.preview_size

    def test_tool_overrides_preserved(self, custom_config: BudgetConfig) -> None:
        """缩放应保留 tool_overrides。"""
        scaled = custom_config.scale_to_context(50_000)
        assert scaled.tool_overrides == dict(custom_config.tool_overrides)

    def test_proportional_result_scaling(self, config: BudgetConfig) -> None:
        """验证 200k 上下文的缩放比例与文档常量一致。"""
        import math as _math

        scaled = config.scale_to_context(200_000)
        expected = max(
            _MIN_RESULT_SIZE_CHARS,
            _math.ceil(200_000 * 4 * 0.15),
        )
        assert scaled.default_result_size == expected

    def test_proportional_turn_scaling(self, config: BudgetConfig) -> None:
        """验证 200k 上下文的 turn_budget 缩放比例。"""
        import math as _math

        scaled = config.scale_to_context(200_000)
        expected = max(
            _MIN_RESULT_SIZE_CHARS * 2,
            _math.ceil(200_000 * 4 * 0.30),
        )
        assert scaled.turn_budget == expected

    def test_returns_new_instance(self, config: BudgetConfig) -> None:
        """缩放应返回新实例, 原实例不变。"""
        scaled = config.scale_to_context(8_000)
        assert scaled is not config
        # 原实例字段未变
        assert config.default_result_size == DEFAULT_RESULT_SIZE_CHARS

    def test_scaled_values_are_int(self, config: BudgetConfig) -> None:
        """缩放后的 default_result_size 和 turn_budget 应为 int。"""
        scaled = config.scale_to_context(128_000)
        assert isinstance(scaled.default_result_size, int)
        assert isinstance(scaled.turn_budget, int)


# ── 4. with_overrides 合并 ────────────────────────────────────────


class TestWithOverrides:
    """with_overrides 方法的合并行为测试。"""

    def test_returns_new_instance(self, config: BudgetConfig) -> None:
        """应返回新的 BudgetConfig 实例。"""
        merged = config.with_overrides({"tool": 100})
        assert merged is not config
        assert isinstance(merged, BudgetConfig)

    def test_adds_new_override(self, config: BudgetConfig) -> None:
        """应正确添加新的 tool_overrides 条目。"""
        merged = config.with_overrides({"custom_tool": 5_000})
        assert merged.resolve_threshold("custom_tool") == 5_000

    def test_preserves_existing_overrides(self, custom_config: BudgetConfig) -> None:
        """已有 override 应被保留。"""
        merged = custom_config.with_overrides({"new_tool": 999})
        assert merged.resolve_threshold("bash") == 10_000
        assert merged.resolve_threshold("my_tool") == 42
        assert merged.resolve_threshold("new_tool") == 999

    def test_overrides_take_precedence_on_collision(self, config: BudgetConfig) -> None:
        """当 key 冲突时, 新传入的值应覆盖旧值。"""
        cfg = config.with_overrides({"tool": 100})
        merged = cfg.with_overrides({"tool": 999})
        assert merged.resolve_threshold("tool") == 999

    def test_original_instance_unchanged(self, config: BudgetConfig) -> None:
        """原实例的 tool_overrides 不应被修改。"""
        config.with_overrides({"tool": 100})
        assert config.tool_overrides == {}

    def test_other_fields_preserved(self, custom_config: BudgetConfig) -> None:
        """非 override 字段应保持不变。"""
        merged = custom_config.with_overrides({"new": 1})
        assert merged.default_result_size == custom_config.default_result_size
        assert merged.turn_budget == custom_config.turn_budget
        assert merged.preview_size == custom_config.preview_size

    def test_empty_overrides_returns_copy(self, config: BudgetConfig) -> None:
        """空 overrides 应返回字段相同的新实例。"""
        merged = config.with_overrides({})
        assert merged is not config
        assert merged.default_result_size == config.default_result_size
        assert merged.tool_overrides == config.tool_overrides


# ── 5. DEFAULT_BUDGET 单例 ────────────────────────────────────────


class TestDefaultBudget:
    """DEFAULT_BUDGET 常量的正确性测试。"""

    def test_is_budget_config_instance(self) -> None:
        """DEFAULT_BUDGET 应为 BudgetConfig 的实例。"""
        assert isinstance(DEFAULT_BUDGET, BudgetConfig)

    def test_uses_default_values(self) -> None:
        """DEFAULT_BUDGET 的字段应与模块级默认常量一致。"""
        assert DEFAULT_BUDGET.default_result_size == DEFAULT_RESULT_SIZE_CHARS
        assert DEFAULT_BUDGET.turn_budget == DEFAULT_TURN_BUDGET_CHARS
        assert DEFAULT_BUDGET.preview_size == DEFAULT_PREVIEW_SIZE_CHARS
        assert DEFAULT_BUDGET.tool_overrides == {}

    def test_resolve_unknown_tool(self) -> None:
        """DEFAULT_BUDGET 对未知工具应回退到默认值。"""
        assert DEFAULT_BUDGET.resolve_threshold("unknown") == float(DEFAULT_RESULT_SIZE_CHARS)

    def test_resolve_pinned_tool(self) -> None:
        """DEFAULT_BUDGET 对置顶工具应返回 inf。"""
        assert math.isinf(DEFAULT_BUDGET.resolve_threshold("read_file"))


# ── 6. TurnBudgetTracker ─────────────────────────────────────────


class TestTurnBudgetTracker:
    """TurnBudgetTracker 的累积、查询和重置行为测试。"""

    # —— 初始状态 ——

    def test_initial_used_is_zero(self, tracker: TurnBudgetTracker) -> None:
        """初始 used 应为 0。"""
        assert tracker.used == 0

    def test_initial_remaining_equals_budget(self, tracker: TurnBudgetTracker) -> None:
        """初始 remaining 应等于 turn_budget。"""
        assert tracker.remaining() == DEFAULT_TURN_BUDGET_CHARS

    def test_initial_not_exceeded(self, tracker: TurnBudgetTracker) -> None:
        """初始 exceeded 应为 False。"""
        assert tracker.exceeded() is False

    def test_initial_tool_count_is_zero(self, tracker: TurnBudgetTracker) -> None:
        """初始 tool_count 应为 0。"""
        assert tracker.tool_count() == 0

    def test_initial_tool_totals_empty(self, tracker: TurnBudgetTracker) -> None:
        """初始 tool_totals 应为空字典。"""
        assert tracker.tool_totals == {}

    # —— record_result 和 remaining ——

    def test_record_single_result(self, tight_tracker: TurnBudgetTracker) -> None:
        """记录单个结果后 used 和 remaining 应正确更新。"""
        tight_tracker.record_result("bash", 300)
        assert tight_tracker.used == 300
        assert tight_tracker.remaining() == 700

    def test_record_multiple_results_accumulate(self, tight_tracker: TurnBudgetTracker) -> None:
        """多次记录应累加字符数。"""
        tight_tracker.record_result("bash", 300)
        tight_tracker.record_result("bash", 200)
        tight_tracker.record_result("read_file", 400)
        assert tight_tracker.used == 900
        assert tight_tracker.remaining() == 100

    def test_tool_totals_defensive_copy(self, tight_tracker: TurnBudgetTracker) -> None:
        """tool_totals 应返回防御性副本, 修改不影响内部状态。"""
        tight_tracker.record_result("bash", 100)
        totals = tight_tracker.tool_totals
        totals["bash"] = 999
        assert tight_tracker.tool_totals["bash"] == 100

    def test_tool_count_distinct_tools(self, tight_tracker: TurnBudgetTracker) -> None:
        """不同工具名称应被分别计数。"""
        tight_tracker.record_result("bash", 100)
        tight_tracker.record_result("bash", 200)
        tight_tracker.record_result("grep", 50)
        assert tight_tracker.tool_count() == 2

    # —— exceeded 检测 ——

    def test_exceeded_just_below_budget(self, tight_tracker: TurnBudgetTracker) -> None:
        """刚好低于预算时 exceeded 应为 False。"""
        tight_tracker.record_result("bash", 999)
        assert tight_tracker.exceeded() is False

    def test_exceeded_at_budget(self, tight_tracker: TurnBudgetTracker) -> None:
        """刚好等于预算时 exceeded 应为 True (>=)。"""
        tight_tracker.record_result("bash", 1000)
        assert tight_tracker.exceeded() is True

    def test_exceeded_over_budget(self, tight_tracker: TurnBudgetTracker) -> None:
        """超过预算时 exceeded 应为 True。"""
        tight_tracker.record_result("bash", 100)
        tight_tracker.record_result("bash", 901)
        assert tight_tracker.exceeded() is True

    def test_remaining_clamped_to_zero(self, tight_tracker: TurnBudgetTracker) -> None:
        """超出预算后 remaining 应截断到 0。"""
        tight_tracker.record_result("bash", 2000)
        assert tight_tracker.remaining() == 0
        assert tight_tracker.exceeded() is True

    # —— 多工具累积 ——

    def test_multi_tool_accumulation(self, tight_tracker: TurnBudgetTracker) -> None:
        """多工具混合使用时 used 应跨工具累加, tool_totals 分开记录。"""
        tight_tracker.record_result("bash", 300)
        tight_tracker.record_result("read_file", 400)
        tight_tracker.record_result("grep", 200)
        tight_tracker.record_result("bash", 200)
        assert tight_tracker.used == 1100
        assert tight_tracker.tool_totals == {
            "bash": 500,
            "read_file": 400,
            "grep": 200,
        }
        assert tight_tracker.exceeded() is True

    # —— reset 清理状态 ——

    def test_reset_clears_used(self, tight_tracker: TurnBudgetTracker) -> None:
        """reset 应将 used 归零。"""
        tight_tracker.record_result("bash", 500)
        tight_tracker.reset()
        assert tight_tracker.used == 0

    def test_reset_restores_remaining(self, tight_tracker: TurnBudgetTracker) -> None:
        """reset 应恢复完整 remaining。"""
        tight_tracker.record_result("bash", 500)
        tight_tracker.reset()
        assert tight_tracker.remaining() == 1_000

    def test_reset_clears_exceeded(self, tight_tracker: TurnBudgetTracker) -> None:
        """reset 应清除 exceeded 状态。"""
        tight_tracker.record_result("bash", 2000)
        assert tight_tracker.exceeded() is True
        tight_tracker.reset()
        assert tight_tracker.exceeded() is False

    def test_reset_clears_tool_totals(self, tight_tracker: TurnBudgetTracker) -> None:
        """reset 应清空 tool_totals。"""
        tight_tracker.record_result("bash", 100)
        tight_tracker.record_result("grep", 200)
        tight_tracker.reset()
        assert tight_tracker.tool_totals == {}
        assert tight_tracker.tool_count() == 0

    def test_reset_on_empty_tracker(self, tight_tracker: TurnBudgetTracker) -> None:
        """空 tracker 上调用 reset 不应报错。"""
        tight_tracker.reset()
        assert tight_tracker.used == 0
        assert tight_tracker.remaining() == 1_000
        assert tight_tracker.exceeded() is False

    # —— 负数 char_count 截断 ——

    def test_negative_char_count_clamped_to_zero(self, tight_tracker: TurnBudgetTracker) -> None:
        """负数 char_count 应被视为 0。"""
        tight_tracker.record_result("bash", 100)
        tight_tracker.record_result("bash", -50)
        assert tight_tracker.used == 100

    def test_negative_char_count_increments_tool_total_safely(self, tight_tracker: TurnBudgetTracker) -> None:
        """负数 char_count 应以 0 加入 tool_totals (不减少)。"""
        tight_tracker.record_result("bash", 100)
        tight_tracker.record_result("bash", -50)
        assert tight_tracker.tool_totals["bash"] == 100

    def test_only_negative_records(self, tight_tracker: TurnBudgetTracker) -> None:
        """全部为负数记录时 used 应保持 0。"""
        tight_tracker.record_result("bash", -100)
        tight_tracker.record_result("grep", -50)
        assert tight_tracker.used == 0
        assert tight_tracker.tool_totals == {"bash": 0, "grep": 0}

    # —— 自定义预算构造 ——

    def test_custom_budget(self) -> None:
        """使用自定义 BudgetConfig 构造 tracker 应正确读取 turn_budget。"""
        cfg = BudgetConfig(turn_budget=500)
        trk = TurnBudgetTracker(budget=cfg)
        assert trk.remaining() == 500
        trk.record_result("tool", 300)
        assert trk.remaining() == 200

    def test_default_budget_constructor(self) -> None:
        """不传参数构造时应使用 DEFAULT_BUDGET。"""
        trk = TurnBudgetTracker()
        assert trk.remaining() == DEFAULT_TURN_BUDGET_CHARS


# ── 7. PINNED_THRESHOLDS 完整性 ──────────────────────────────────


class TestPinnedThresholds:
    """PINNED_THRESHOLDS 常量的完整性和不可变性测试。"""

    @pytest.mark.parametrize("tool_name", ["read_file", "glob", "grep"])
    def test_specific_pinned_tools(self, config: BudgetConfig, tool_name: str) -> None:
        """read_file、glob、grep 三个关键工具应返回 inf。"""
        assert math.isinf(config.resolve_threshold(tool_name))

    def test_all_pinned_values_are_inf(self) -> None:
        """PINNED_THRESHOLDS 中所有值都应为 math.inf。"""
        for name, value in PINNED_THRESHOLDS.items():
            assert math.isinf(value), f"{name} 的值应为 inf, 实际: {value}"

    def test_pinned_tools_count(self) -> None:
        """PINNED_THRESHOLDS 应包含预期的 8 个工具。"""
        assert len(PINNED_THRESHOLDS) == 8

    def test_pinned_tool_names(self) -> None:
        """PINNED_THRESHOLDS 应包含所有预期的工具名称。"""
        expected = {
            "read_file",
            "read_multiple_files",
            "glob",
            "grep",
            "list_dir",
            "list_project_files",
            "web_fetch",
            "web_search",
        }
        assert set(PINNED_THRESHOLDS.keys()) == expected