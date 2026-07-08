# Butler v4 — 形式化理论复验（2026-07）

> **版本**：2026-07-08  
> **基线**：[`formal-theory-2026-06.md`](formal-theory-2026-06.md)（2026-06-12 分析包）  
> **层映射 SSOT**：[`../layer-theory-engineering-map.md`](../layer-theory-engineering-map.md)  
> **理论 SSOT**：[`../v4-theoretical-baseline.md`](../v4-theoretical-baseline.md) v3.1.2  
> **差距登记**：[`../../plans/decisions/theory-implementation-gap-register-2026-06.md`](../../plans/decisions/theory-implementation-gap-register-2026-06.md)

---

## 0. 复验结论摘要

九层竖切（P2–P5，2026-07-07）与 `CYCLE_KEEP` 清零**不改变** T1–T10 / MT / CT 证明逻辑；竖切将若干前提的**工程锚点**迁移到 contracts Port 与独立模块。本次复验：

| 类别 | 数量 | 结果 |
|------|------|------|
| 主定理 T1–T10 | 10 | ✅ 前提仍成立 |
| 观测 OT1–OT2 | 2 | OT1 ✅；OT2 观测中（G1-04） |
| 记忆 MT1–MT7 | 7 | ✅（工程层索引 L5） |
| 开发 CT1–CT5 | 5 | ✅ |
| 契约公理 A12–A13 | 2 | ✅ 新增，与 P2f 一致 |
| **冲突 ❌** | 0 | — |

**政策**：证明正文（v3.1.1 第三–七章）未改；本文件仅增工程层列与竖切后模块名。

---

## 1. 主定理复验矩阵

| 定理 | 理论层 | **工程层** | 竖切后关键模块 | 复验 | 测试入口 |
|------|--------|------------|----------------|------|----------|
| T1 上下文不溢出 | L2 | L3 + L6 | `context_pipeline*`, `context_transform_registry` | ✅ | context / premise P3 tests |
| T2 队列收敛 | L1 | L1 + L8 | `message_queue`, `queue_settings` | ✅ | `test_premise_p4_queue_drain` |
| T3 权限不可提升 | L6 | L4 + L7 | `permissions/rules_fail_closed_ops`, `tool_orchestrator` | ✅ | `test_premise_p5`, `test_r2_11_permissions_fail_closed` |
| T4 记忆不污染 | L6 | L3 + L5 | `RecallRouter`, `memory_prefetch`, `session_transcript` | ✅ | `test_premise_memory_theory` |
| T5 DAG 终止 | L5 | L2 | `task_orchestrator`, `workflows/runner` | ✅ | orchestrator tests |
| T6 信息流安全 | L6 | L2 + L7 | `ApprovalStore`, `WorkflowGateStore`, `human_gate` | ✅ | `test_p2_workflow_permissions` |
| T7 PIM 有界 | L3 | L4 | `tenant.py`, PIM tools | ✅ | `test_premise_v3*` |
| T8 管家-委派分离 | L6 | L2 + L4 | `project_tools._butler_allowed_tools`, gate pipeline | ✅ | delegate / premise P5 |
| T9 编辑可回滚 | L4 | L4 | `dev_engine/edit_ops` | ✅ | dev_engine tests |
| T10 Dev 终止 | L4 | L4 | `dev_loop`, doom loop | ✅ | `test_premise_coding_knowledge` |
| OT1 软反馈有界 | L7 | L3 + L9 | `eval_feedback`, ephemeral inject | ✅ | orchestration tests |
| OT2 硬反馈收敛 | L7 | L9 | `eval_actions`, G1-04 窗 | ⏳ 观测 | `butler-g1-04-weekly-checkin.sh` |

---

## 2. 竖切后重点前提复验

| 前提 | 变更前锚点 | **竖切后锚点** | 复验 |
|------|------------|----------------|------|
| P-T3b dispatch 检查 | `registry` 直引 | `tool_orchestrator` + `ToolRegistryReadPort` | ✅ |
| P-T8d 写工具隔离 | `project_tools` | 不变 + gate pipeline | ✅ |
| P-T4a pre_llm 副本 | `memory_prefetch` | + `RecallRouter` / `unified_hybrid_search` | ✅ |
| P-T6 workflow 审批 | `human_gate` 分散 | `ApprovalStore` + `WorkflowGateStore` | ✅ |
| P-OT1a ephemeral | `agent_loop` | 不变 | ✅ |
| P-OT2c 生产度量 | L2 metrics | L9 `runtime_metrics` + `/诊断` | ⏳ G1-04 |

---

## 3. 子理论层号 → 工程层

| 子理论 | 文档内层号 | **工程层** | 复验 |
|--------|------------|------------|------|
| `v4-memory-theory.md` | 称 L6 | **L5** | MT1–MT7 ✅ |
| `v4-dev-engine-theory.md` | 称 L4 | **L4** (+ L3 delegate) | CT1–CT5 ✅ |
| `v4.5-modular-eval-context-theory.md` | — | L3 + L9 + contracts | T-CTX-1/2 ✅ |

---

## 4. 记忆子理论 MT1–MT7 逐条复验

| 定理 | 陈述要点 | **工程层** | 竖切后锚点 | 复验 | 测试 |
|------|----------|------------|------------|------|------|
| MT1 | 写入原子性（Store∧Index 或 NoOp） | L5 | `memory/facade.py`, `reindex.py` | ✅ | P-MT1a/b/c |
| MT2 | 检索完备性（存在 q 可召回） | L5 | `semantic_index.py`, `RecallRouter`, `unified_hybrid_search` | ✅ | P-MT2a/b/c |
| MT3 | 域隔离（Tenant/Project 路径不交） | L5 | `tenant.py`, `tenant_memory_dir` | ✅ | P-MT3* |
| MT4 | 注入不污染 transcript（≈T4） | L3+L5 | `memory_prefetch`, `session_transcript` | ✅ | premise memory |
| MT5 | 衰减单调；安全遗忘 | L5 | `type_adjusted_half_life`, decay 策略 | ✅ | P-MT5* |
| MT6 | 每层容量有界 | L5 | ranking / eviction 策略 | ✅ | — |
| MT7 | 持久化与索引最终一致 | L5 | `reindex_semantic_memory` 兜底 | ✅ 诚实边界 | G2-09 登记 |

**竖切影响**：记忆 CLI pending 自 gateway 迁至 `memory/pending_handlers.py`；不改变 MA/MT 证明链。Langfuse 遥测改为 `memory_prefetch_ops` 函数内 lazy import（L5→L9 allowlist）。

---

## 5. 编码知识层 CT1–CT5 逐条复验

| 定理 | 陈述要点 | **工程层** | 竖切后锚点 | 复验 | 测试 |
|------|----------|------------|------------|------|------|
| CT1 | 定理验证器可检结构违规 | L4 | `dev_engine/theorem_library`, dual_verify | ✅ | P-CT1 (22/22) |
| CT2 | 无经验时纯定理推理仍保逻辑骨架 | L4 | 经验降级路径 + gate | ✅ | P-CT2 (4/4) |
| CT3 | 经验入库须全量定理检查 | L4 | `coding_knowledge` 入库门 | ✅ | premise CA3 |
| CT4 | 激活函数选择相关定理子集 | L4 | task-kind / delegate 路由 | ✅ | delegate tests |
| CT5 | dual_verify 门控输出 | L4 | `b9_delegate_gate_ops` → `delegate.task_kind` | ✅ | P-CT* |

**竖切影响**：`b9_delegate_gate_ops` 改引 L4 `task_kind`（破 gateway 环）；CA4 strict advisory 仍为 G2-08 开放项，不推翻 CT5 默认边界。

---

## 6. 契约公理（v3.1.2 新增）

| ID | 陈述 | 工程实例 | 复验 |
|----|------|----------|------|
| A12 | contracts Protocol/Registry 不 import 实现方；`*_impl.py` bootstrap 除外 | `butler/contracts/README.md` 依赖规则 | ✅ ENG-15 |
| A13 | 层间环经 Port/registry | P2f `CYCLE_KEEP` 清零 | ✅ lazy budget |

---

## 7. 开放项（非证明冲突）

| ID | 项 | 对推导影响 |
|----|-----|------------|
| G1-04 | OT2 生产窗观测 | 不推翻 OT2；有条件目标 |
| G2-08 | CA4 strict advisory | 不推翻 CT5；默认边界 |

---

## 8. 相关文档

- 完整定理陈述：[`formal-theory-2026-06.md`](formal-theory-2026-06.md)  
- 解耦评估：[`decoupling-assessment-2026-07.md`](decoupling-assessment-2026-07.md)  
- 九层模型：[`../v4-layer-model.md`](../v4-layer-model.md)
