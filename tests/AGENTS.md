# Butler Tests — 测试模块

> **层级**：测试 / 验证  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
tests/
├── conftest.py                    # 测试配置
├── test_*.py                      # 各模块测试
├── gateway/                       # Gateway 测试
├── ops/                           # Ops 测试
└── （其他测试子目录）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `gateway/` | Gateway 测试 | 消息处理、队列等测试 |
| `ops/` | Ops 测试 | 运营模块测试 |

## 关键测试文件

| 文件 | 说明 | 覆盖范围 |
|------|------|----------|
| `test_cc_p3_p4_features.py` | CC 线束测试 | P3/P4 特性 |
| `test_tool_result_storage.py` | 工具结果存储 | 工具调用 |
| `test_premise_memory_theory.py` | 记忆理论测试 | 记忆子理论 |
| `test_premise_coding_knowledge.py` | 编码知识测试 | CA1-CA4/CT1-CT5 |
| `test_engineering_bridge.py` | 工程桥接测试 | D3-7/8/9 |

## 测试门禁

```bash
# 快速门禁（约 3–5 分钟）
./scripts/butler-pytest-fast-gate.sh

# mypy strict 门禁
bash scripts/butler-mypy-strict-gate.sh

# 层依赖门禁
bash scripts/butler-layer-import-gate.sh

# CC 线束门禁
./scripts/butler-cc-harness-gate.sh

# 按域测试
bash scripts/butler-domain-pytest.sh gateway  # ops | dev_engine | memory | core
```

## 注意事项

1. **测试策略**：参考 [`docs/plans/decisions/agent-testing-strategy-2026-06.md`](../docs/plans/decisions/agent-testing-strategy-2026-06.md)
2. **Live LLM**：部分测试需要真实 LLM 调用，通过 `LIVE_LLM=1` 启用
3. **Mock LLM**：`test_llm_response_fixtures.py` 提供 mock LLM 测试

## 相关目录

- L3 核心：[`butler/core/`](../butler/core/)
- L1 Gateway：[`butler/gateway/`](../butler/gateway/)
