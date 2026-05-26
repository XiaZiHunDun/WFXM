# 微信真实语料 — 维度覆盖矩阵

> 权威数据：`tests/corpus/suites/wechat_real/lw_real/meta.yaml` 中 `coverage_matrix`。  
> 本页供人工 review；CI 门禁见 `tests/corpus/runners/test_gateway_module_health.py`。

## 分层说明

| 符号 | 含义 |
|------|------|
| **L0 smoke** | `reference_utterance_catalog.yaml`，在册 + 去重，不跑 gateway |
| **L1 strict** | 主目录 + `reference_utterance_strict` + `production`，mock 严断言 |
| **L1 multiturn** | `utterance_multiturn_catalog.yaml` |
| **L2 golden** | `test_gateway_dev_conversations.py` 手写整链 |

## 维度覆盖（2026-05-24）

| 维度 | 说明 | L0 | L1 strict | Multiturn | 备注 |
|------|------|:--:|:---------:|:---------:|------|
| A | 项目/会话 | ✓ | ✓ | ✓ | MT-01,04 |
| B | 只读探查 | ✓ | ✓ | ✓ | MT-19 |
| C | 委派写删 | ✓ | ✓ | ✓ | MT-13,07,10 |
| D | 详细报告 | ✓ | ✓ | ✓ | MT-02,03,17 |
| E | 记忆运维 | ✓ | ✓ | — | 可加 MT |
| F | 工作流/定时 | ✓ | ✓ | — | |
| G | 安全边界 | ✓ | ✓ | ✓ | MT-08,20 |
| H | 能力介绍 | ✓ | ✓ | — | |
| I | 小说工厂 | ✓ | ✓ | — | workflow_state |
| J | 多轮链（源） | ✓ | 部分 | ✓ | MT-12,14 |
| K | 情绪催促 | ✓ | ✓ | — | 保留少量 generic_ack |
| L | 跨项目 | ✓ | ✓ | ✓ | MT-16,18 |
| N～V | 扩展类 | ✓ | ✓ | 部分 | 见 strict REAL-* |

## 待补格（优先级）

1. **E/F + 多轮**：记忆待审 → 追问 → /状态。  
2. **P + 多轮**：连发两条短消息（需产品支持或 mock 合并）。  
3. **J 完整改口链**：MT-14 已覆盖，可再加 1 条 ≥6 轮。  
4. **L3 live**：`meta.live_smoke_ids` 挂接 catalog（阶段 3）。

## 更新方式

1. 改 `reference/用户语料` 或手册 YAML → 跑生成脚本。  
2. 更新 `meta.yaml` 的 `coverage_matrix` 与 `targets`。  
3. `pytest tests/corpus/runners/test_gateway_module_health.py -q`。
