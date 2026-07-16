#!/bin/bash
#分层测试运行脚本 - 根据标记执行不同层级的测试

set -e

PYTEST_CMD="python3 -m pytest"
LAYER="${1:-l0}"
VERBOSE="${2:-false}"

case "$LAYER" in
    l0)
        echo "=== 运行 L0 快速单元测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py -q --tb=short
        fi
        ;;
    l1)
        echo "=== 运行 L1 集成测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l1_integration.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l1_integration.py -q --tb=short
        fi
        ;;
    l0-l1)
        echo "=== 运行 L0 + L1 测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py -q --tb=short
        fi
        ;;
    l2)
        echo "=== 运行 L2 场景/边界/不变量测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py -q --tb=short
        fi
        ;;
    l2-scenario)
        echo "=== 运行 L2 场景测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_scenario_parametrized.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_scenario_parametrized.py -q --tb=short
        fi
        ;;
    l2-property)
        echo "=== 运行 L2 不变量测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_property_invariants.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_property_invariants.py -q --tb=short
        fi
        ;;
    l2-edge)
        echo "=== 运行 L2 边界条件测试 ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_edge_cases.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l2_edge_cases.py -q --tb=short
        fi
        ;;
    l3)
        echo "=== 运行 L3 真实LLM端到端测试 ==="
        echo "注意: 需要配置 DEEPSEEK_API_KEY 或 MINIMAX_API_KEY"
        echo "正在加载 .env 文件..."
        if [ -f .env ]; then
            export $(grep -v '^#' .env | xargs)
        fi
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l3_e2e_real_llm.py -v --tb=short -o addopts=""
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l3_e2e_real_llm.py -q --tb=short -o addopts=""
        fi
        ;;
    all)
        echo "=== 运行所有测试 (L0 + L1 + L2) ==="
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py -v --tb=short
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py -q --tb=short
        fi
        ;;
    all-live)
        echo "=== 运行所有测试 (L0 + L1 + L2 + L3) ==="
        echo "正在加载 .env 文件..."
        if [ -f .env ]; then
            export $(grep -v '^#' .env | xargs)
        fi
        if [ "$VERBOSE" = true ]; then
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py tests/test_l3_e2e_real_llm.py -v --tb=short -o addopts=""
        else
            PYTHONPATH=. $PYTEST_CMD tests/test_l0_unit_fast.py tests/test_l1_integration.py tests/test_l2_scenario_parametrized.py tests/test_l2_property_invariants.py tests/test_l2_edge_cases.py tests/test_l3_e2e_real_llm.py -q --tb=short -o addopts=""
        fi
        ;;
    *)
        echo "用法: $0 [l0|l1|l0-l1|l2|l2-scenario|l2-property|l2-edge|l3|all|all-live] [verbose]"
        echo ""
        echo "测试分层说明:"
        echo "  l0:         快速单元测试 (~50条, <1秒) - 每轮提交运行"
        echo "  l1:         集成测试 (~150条, <60秒) - PR时运行"
        echo "  l0-l1:      L0 + L1 组合"
        echo "  l2:         L2层全部测试 (~300条, <5分钟) - 合并前运行"
        echo "  l2-scenario:    L2场景测试 (~200条)"
        echo "  l2-property:    L2不变量测试 (~50条)"
        echo "  l2-edge:        L2边界条件测试 (~50条)"
        echo "  l3:         真实LLM端到端测试 (10条, ~20秒) - 发布时运行"
        echo "  all:        L0 + L1 + L2 全部测试"
        echo "  all-live:   L0 + L1 + L2 + L3 全部测试(含真实LLM)"
        echo ""
        echo "示例:"
        echo "  $0 l0              # 快速运行基础测试"
        echo "  $0 l0-l1           # PR检查"
        echo "  $0 l2              # 合并前完整检查"
        echo "  $0 l3              # 真实LLM测试"
        echo "  $0 all             # 全部测试"
        echo "  $0 all-live        # 全部测试(含真实LLM)"
        echo "  $0 l0 true         # 详细输出"
        exit 1
        ;;
esac

echo ""
echo "测试完成!"
