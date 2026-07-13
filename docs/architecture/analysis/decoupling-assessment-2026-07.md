# Butler v4 — 层次解耦评估（2026-07）

> **日期**：2026-07-08（P1–P4 收口）  
> **范围**：P2–P5 竖切后九层 + contracts  
> **门禁**：ENG-7（core/tools ↔ gateway）、**ENG-15**（全层依赖矩阵）  
> **层映射**：[`layer-theory-engineering-map.md`](../layer-theory-engineering-map.md)

---

## 1. 结论

| 维度 | 状态 | 说明 |
|------|------|------|
| **概念解耦** | ✅ 已达成 | 九层 + 理论七层映射 SSOT；§9 决策树可定位新模块 |
| **契约封装** | ✅ 已达成 | `CYCLE_KEEP` 清零；15+ Port；A12–A13 入理论 v3.1.2 |
| **自动化守门** | ✅ 已扩展 | ENG-15 **1218 passed / 0 违规**（2026-07-08 P1–P2 收口） |
| **包映射覆盖** | ✅ 1218/1218 | P1–P4 后补全 `config/`、`defaults/`、`tests_policies/` 等顶层模块 |
| **热路径 ↔ L9** | ⚠️ 文档化 seams | L3/L5 经 allowlist 引 `runtime_metrics` 等；非硬依赖 eval 重模块 |
| **剩余 lazy import** | ⚠️ 预算内 | ~1901 / budget 1910；非环，多为启动/可选路径 |

**总体**：各层**可从领域上定位**；**内部替换**在遵守 Port 与 ENG-15 时不必动他层。尚未「完全物理隔离」的项见 §3，已列为 Backlog 或 allowlist。

---

## 2. ENG-15 首跑（2026-07-08）

命令：`bash scripts/butler-layer-import-gate.sh`（或 `collect_all_violations()`）

| 结果 | 数量 |
|------|------|
| 扫描文件 | butler/**/*.py（不含 contracts/） |
| **映射覆盖** | **1218 / 1218**（100%） |
| 违规（修复/allowlist 前） | 6 |
| **当前违规** | **0** |

### 2.1 P2 模块迁移（已消除原 allowlist 项）

| 原违规 | 处置 |
|--------|------|
| `dev_engine/b9_delegate_gate_ops` → gateway | ✅ 改引 `butler.delegate.task_kind` |
| `delegate/task_kind` → `gateway.owner_ingest_shortcuts` | ✅ 下沉至 `butler/delegate/owner_ingest_shortcuts.py`；gateway 为 re-export shim |
| `human_gate` → `gateway.gate_reply_templates` | ✅ 上提至 `butler/gate_reply_templates.py`（L7） |
| `model_resolve_ops` → gateway 媒体探测 | ✅ 迁至 `gateway/media_diagnostic_ops.py`；L6/L9 诊断路径组合调用 |
| `memory/pending_cli` → gateway handlers | ✅ 核心逻辑迁至 `memory/pending_handlers.py` + `pending_command_ops.py` |

**新增 Port**：`InboundIdempotencyPort`（`session/new_session_ops` 经 registry，无 gateway fallback）。

### 2.2 当前 gateway allowlist（仅 1 项）

定义：[`tests/layer_import_rules.py`](../../../tests/layer_import_rules.py) `FILE_GATEWAY_IMPORT_ALLOWLIST`。

| 文件 | 层 | 理由 |
|------|-----|------|
| `butler/execution_context.py` | L3 | Loop 与 gateway handler 共享的会话执行上下文；ENG-7 历史 seam |

**已移除**（P2 后不再 allowlist）：`task_kind`、`human_gate`、`model_resolve_ops`、`pending_cli`。

### 2.3 L3 → L9 遥测 allowlist

`core/` 可 import 下列 **best-effort** 模块（矩阵 L3→L9 读）：

- `butler.ops.runtime_metrics`
- `butler.ops.retry_buckets`
- `butler.ops.cost_tracker`
- `butler.ops.usage_ledger`
- `butler.ops.eval_actions` / `eval_feedback`

禁止 L3 引 `health_report`、`eval_integration` 等重 L9 模块（当前无违规）。

### 2.4 L5 → L9 遥测 allowlist（新增）

`memory/` 可 lazy import：

- `butler.ops.langfuse_tracer`（`memory_prefetch_ops` 函数内）
- `butler.ops.runtime_metrics`
- `butler.ops.embedding_diagnostics` / `transcript_diagnostics`
- `butler.ops.degradation_registry`
- `butler.ops.eval_config_overrides`

---

## 3. 剩余耦合项

### 3.1 顶层 import 环（已预算，非 CYCLE_KEEP）

| 环 | 状态 | 建议 |
|----|------|------|
| `delegate_impl` ↔ `orchestrator` | `delegate_orchestrator` 隔离 lazy | 可选：进一步 Port 化 |
| ~1901 函数内 lazy import | P3-I budget 1910 | contracts 完成后继续减量 |

### 3.2 A12 弱形式张力（已收口 / 登记）

| 位置 | 现象 | 状态 |
|------|------|------|
| `contracts/*_impl.py` | impl 片 import L4/L7 并注册 | ✅ 允许：bootstrap 注册（A12 明文） |
| `health_diagnostic_ports.py` | 曾 import `ops.health_report_input` | ✅ `HealthReportInput` 迁至 `contracts/health_report_input.py` |
| `execution_context.py` | L3 唯一 gateway allowlist | ENG-7 遗留；替换需 Port 或上下文注入 |

理论 v3.1.2 **A12** 已区分：Protocol/Registry **定义**不得 import 实现方；`*_impl.py` 引导注册片除外。

### 3.3 层边界模糊（文档已澄清）

- **L2 vs L3**：Loop 工厂在 L2（`orchestrator/loop_factory`），认知环在 L3（`core/agent_loop`）— 见 [`v4-layer-model.md`](../v4-layer-model.md) §9.2
- **L8 vs L1**：`message_queue` 在 gateway 包内，逻辑属 L8 — 选型时按职责而非目录

### 3.4 未映射文件

**无**（2026-07-08 补全：`config*`→L1、`context_settings*`→L3、`memory_settings*`→L5、`provider_presets*`→L6、`defaults/model_defaults`→L6、其余 `defaults/`/`tests_policies/` 按前缀）。

### 3.5 已「概念解耦 + 封装可换」的层

| 层 | 证据 |
|----|------|
| L3 ↔ L1 | ENG-7 + ENG-15；`execution_context`（唯一 allowlist） |
| L4 工具 | `ToolRegistryReadPort`、`ToolDispatchPort` |
| L5 记忆 | `RecallRouter`、`memory_ports`、`pending_handlers` |
| L6 模型 | `format_model_diagnostic_lines` 不含 gateway；媒体诊断组合于 L9 |
| L7 策略 | `ApprovalStore`、`WorkflowGateStore`、`gate_reply_templates` |
| L9 诊断 | `HealthDiagnosticPort` + `health_report` 组合 gateway 媒体行 |

---

## 4. 新模块引入流程（摘要）

1. §9 决策树定层  
2. 若跨层 → 增 contracts Port  
3. 跑 `butler-layer-import-gate.sh`  
4. 更新 [`layer-theory-engineering-map.md`](../layer-theory-engineering-map.md)（若影响定理/前提锚点）

---

## 5. 相关文档

- [`formal-theory-2026-07.md`](formal-theory-2026-07.md) — 定理复验（含 MT/CT 逐条表）  
- [`butler/contracts/README.md`](../../../butler/contracts/README.md) — Port 清单  
- [`project-optimization-directions-2026-06.md`](../../plans/active/project-optimization-directions-2026-06.md) §S2 — lazy import 基线
