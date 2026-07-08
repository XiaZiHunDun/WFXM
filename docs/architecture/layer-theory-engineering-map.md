# Butler v4 — 理论层 ↔ 工程层映射 SSOT

> **状态**：2026-07-08  
> **用途**：定理/前提复验、新模块归属、文档交叉引用时的**单页映射表**。  
> **工程分层 SSOT**：[`v4-layer-model.md`](v4-layer-model.md)  
> **理论 SSOT**：[`v4-theoretical-baseline.md`](v4-theoretical-baseline.md) v3.1.2（七层产品域 + 五元组）  
> **契约 SSOT**：[`butler/contracts/README.md`](../../butler/contracts/README.md)

---

## 1. 为何两套「L1–L7」并存

| 视角 | 文档 | 层数 | 回答的问题 |
|------|------|------|------------|
| **产品/领域** | `v4-theoretical-baseline.md` §2 | 七层 | Owner 看到什么能力、公理/定理归属哪个业务域 |
| **实现/依赖** | `v4-layer-model.md` | 九层 + 契约 | 代码包如何依赖、换组件时动哪一层 |
| **形式化** | 五元组 \((\mathcal{G}, \mathcal{L}, \Pi, \mathcal{M}, \mathcal{A})\) | — | 概念建模与证明链入口 |

**不是简单重编号**：理论 L2「管家智能」= 工程 **L2 编排 + L3 认知环**；理论 L6「记忆+安全」= 工程 **L5 记忆 + L7 策略**。

---

## 2. 总映射表

| 理论层（产品域） | 五元组 | 工程层 | 主要代码路径 | 代表定理/公理 |
|------------------|--------|--------|--------------|---------------|
| **L1 WeChat 界面** | \(\mathcal{G}\) | **L1** 接入 + **L8** 队列/outbox | `gateway/`, `cli/`, `message_queue`, `durable_outbox` | T2 队列收敛；命题 2.2–2.4 |
| **L2 管家智能** | \(\mathcal{L}\) + 路由 | **L2** 编排 + **L3** 认知环 | `orchestrator/`, `core/agent_loop*`, `context_pipeline*` | T1 上下文；T8 委派分离；OT1 软反馈 |
| **L3 PIM** | \(\Pi_I\) | **L4** 工具（tenant 工具集） | `tenant.py`, `tools/{contacts,memo,...}` | T7 PIM 有界；P-PIM 路由 |
| **L4 开发引擎** | \(\Pi_D\) | **L4** dev_engine + delegate | `dev_engine/`, `tools/delegate*`, `runtime/delegate_job` | T9 回滚；T10 Dev 终止；DT/CT 子理论 |
| **L5 项目管理** | \(\Pi_P\) | **L2** workflows + **L4** project_todos | `workflows/`, `project/`, `runtime/` | T5 DAG 终止；T6 门控 |
| **L6 记忆与安全** | \(\mathcal{M}\) + \(\mathcal{A}\) | **L5** 记忆 + **L7** 策略 | `memory/`, `permissions/`, `human_gate.py` | T4 记忆不污染；T3/T6/T8；MT/MA 子理论 |
| **L7 观测演化** | OA1–OA3 | **L9** 运营 | `ops/`, `eval_integration/`, `report/` | OT1–OT2 |
| — | — | **L6** 模型协议 | `transport/`, `model_resolve*` | P-T1 token 估算；failover |
| — | — | **横切** contracts | `butler/contracts/` | A12–A13；v4.5 A8–A11 |

---

## 3. 主定理 → 工程层 → 模块 → 测试

| 定理 | 坚实度 | 工程层 | 竖切后关键模块（2026-07） | 测试入口 |
|------|--------|--------|---------------------------|----------|
| **T1** 上下文不溢出 | L4 | L3 + L6 | `context_pipeline*`, `context_compressor`, `reactive_compact` | `test_premise_p3*`, context tests |
| **T2** 队列收敛 | L2 | L1 + L8 | `message_queue`, `message_handler` | `test_premise_p4_queue_drain`, `test_message_queue` |
| **T3** 权限不可提升 | L3 | L4 + L7 | `delegate/policy`, `permissions/`, `tool_orchestrator` gate | `test_premise_p5`, `test_r2_11_permissions_fail_closed` |
| **T4** 记忆不污染 | L1 | L3 + L5 | `memory_prefetch`, `RecallRouter`, `session_transcript` | `test_premise_memory_theory`, `test_memory_p1_p2` |
| **T5** DAG 终止 | L2 | L2 | `task_orchestrator`, `workflows/runner` | task_orchestrator tests |
| **T6** 信息流安全 | L1 | L2 + L7 | `human_gate`, `ApprovalStore`, `WorkflowGateStore` | `test_p2_workflow_permissions` |
| **T7** PIM 有界 | L2 | L4 | `tenant.py`, `pim_schema`, PIM tools | `test_premise_v3*` |
| **T8** 管家-委派分离 | L3 | L2 + L4 | `project_tools._butler_allowed_tools`, `tool_orchestrator` | `test_premise_p5`, delegate tests |
| **T9** 编辑可回滚 | L1 | L4 | `dev_engine/edit_ops`, EditHistory | dev_engine tests |
| **T10** Dev 循环终止 | L2 | L4 | `dev_engine/dev_loop`, doom loop guard | `test_premise_coding_knowledge` |
| **OT1** 软反馈有界 | L1 | L3 + L9 | `eval_feedback`, `_turn_ephemeral_system` | `test_orchestration_improvements` |
| **OT2** 硬反馈收敛 | 有条件 | L9 | `eval_actions`, G1-04 运营窗 | `butler-g1-04-weekly-checkin.sh` |

### 子理论索引（层号修正）

| 子理论 | 理论文档层号 | **工程层** | 符号 |
|--------|--------------|------------|------|
| 记忆 | 父理论称 L6 | **L5** | MA1–MA7, MT1–MT7, MB1–MB7 |
| 开发引擎 | 理论 L4 | **L4**（+ L3 delegate 路径） | DA1–DA7, DT1–DT7, CA1–CA4, CT1–CT5 |
| Eval/Context | v4.5 扩展 | L3 + L9 + contracts | A8–A11, T-CTX-* |

---

## 4. 前提 P-* 工程锚点（竖切后）

| 前提族 | 工程层 | 竖切后模块 | 复验 |
|--------|--------|------------|------|
| P-T2* 队列 | L1/L8 | `message_queue`, `queue_settings` | ✅ |
| P-T3/T8/P5 权限 | L4/L7 | `permissions/rules_fail_closed_ops`, `tool_orchestrator`, `ApprovalStore` | ✅（含 TCR 权限 fix 2026-07-08） |
| P-T4/P6 记忆/门控 | L3/L5/L7 | `RecallRouter`, `unified_hybrid_search`, `WorkflowGateStore` | ✅ |
| P-OT* 观测 | L9 | `eval_integration/`, `ops/eval_*`, `/诊断` | OT1 ✅；OT2 观测中（G1-04） |
| P-MT* 记忆 | L5 | `memory/facade`, `semantic_index`, `post_session` | ✅ 27 tests |
| P-CT*/H* 编码知识 | L4 | `coding_knowledge`, `verify.py`, CA4 strict opt-in | ✅；G2-08 advisory 默认 |

---

## 5. 契约 Port → 工程层（P2f 竖切）

| Port | 服务层 | 典型实现 |
|------|--------|----------|
| `BridgeAccess` / `OutboundCompletionHooks` | L1↔L3 | `outbound_bridge`, `completion_notify` |
| `ToolRegistryReadPort` | L4 | `tools/registry` |
| `ToolDispatchPort` | L3 | `core/tool_dispatch` |
| `LoopMemoryView` / compaction ports | L3↔L5 | core context 管线 |
| `ApprovalStore` / `WorkflowGateStore` | L7 | `approval_store_impl`, `workflow_gate_impl` |
| `HealthDiagnosticPort` | L9 | `ops/health_report_turn` |
| `EvalSuitePort` / `ContextTransformPort` | L9 / L3 | v4.5 扩展 |

新跨层能力：**先增 Port → registry 注册 → 再删 lazy import**（公理 A13）。

---

## 6. 新模块快速定位

详见 [`v4-layer-model.md`](v4-layer-model.md) §9 决策树。本表为缩写：

| 若新能力是… | 归属 |
|-------------|------|
| Owner 微信/CLI 可见交互 | L1 |
| 会话/workflow/delegate 生命周期 | L2 |
| 单轮 Loop（context/LLM/tool） | L3 |
| 可注册工具/MCP/Skill/DevEngine | L4 |
| 持久记忆/召回/Experience | L5 |
| LLM/Embedding 协议 | L6 |
| 权限/审批/路径安全 | L7 |
| 队列/outbox/重试/降级 | L8 |
| 诊断/eval/报告 | L9 |
| 跨层稳定接口 | **contracts** 先行 |

---

## 7. 相关文档

| 文档 | 关系 |
|------|------|
| [`v4-layer-model.md`](v4-layer-model.md) | 九层定义、依赖矩阵、选型 |
| [`v4-theoretical-baseline.md`](v4-theoretical-baseline.md) | 公理/定理证明正文 |
| [`analysis/formal-theory-2026-07.md`](analysis/formal-theory-2026-07.md) | 前提复验矩阵（2026-07） |
| [`analysis/decoupling-assessment-2026-07.md`](analysis/decoupling-assessment-2026-07.md) | ENG-15 解耦评估 |
| [`theory-implementation-gap-register-2026-06.md`](../plans/decisions/theory-implementation-gap-register-2026-06.md) | G1–G4 登记 |
