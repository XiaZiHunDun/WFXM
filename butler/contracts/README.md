# `butler/contracts` — 层间契约

> **架构分层**：见 [`docs/architecture/v4-layer-model.md`](../../docs/architecture/v4-layer-model.md)（九层 + 本目录为**横切契约层**）。  
> **ENG-6 / P1-D**：`core/`、`tools/` 通过 Port 访问 gateway/记忆/压缩视图，避免直引 `gateway.*`。

## 用途

- 定义 **Protocol / 只读 View / Registry**，供上层依赖接口、下层提供实现。
- 新组件选型时：**先增或复用 Port → 实现注册 → 再删环依赖 lazy import**。
- Gateway 启动时调用 `register_gateway_contracts()` / `register_gateway_events_sink()` 注入实现。

## Port 与分层映射

| 模块 | 主要类型 | 服务层 | 典型实现方 |
|------|----------|--------|------------|
| `events.py` | `EventsSink` | L1↔L3 事件 | `gateway/events_sink_impl.GatewayEventsSink` |
| `owner_gate.py` | `OwnerGate` | L7 策略 | gateway 注册 |
| `bridge_access.py` | `BridgeAccess` | L1 出站 | `outbound_bridge` / `completion_notify` |
| `memory_ports.py` | `LoopMemoryView` | L5 记忆 | core 压缩/编排读取 |
| `compaction_ports.py` | `LoopCompactionView` | L3 上下文 | core context 管线 |
| `message_ports.py` | `LoopApiMessageView` | L3 消息形态 | core / transport 边界 |
| `dev_context_ports.py` | `DevVerifyView` | L4 DevEngine | `dev_engine` ↔ core 适配 |
| `dev_state_ports.py` | `LoopDevStateView` | L4 DevEngine | delegate 子 loop |
| `review_ports.py` | `DevReviewView` | L4 审查 | `dev_review` 路径 |
| `hook_context_ports.py` | `HookContextView` | L4 Hook | hooks runner |
| `context_transform_ports.py` | `ContextTransformPort` | L3 上下文 | 可插拔 transform |
| `eval_ports.py` | `EvalSuitePort`, `ScoreSinkPort` | L9 运营 | `eval_integration` |

## Registry

| 模块 | API |
|------|-----|
| `sink_registry.py` | `get_events_sink` / `set_events_sink` |
| `gateway_registry.py` | `get_owner_gate` / `set_owner_gate`、`get_bridge_access` / `set_bridge_access` |

## 竖切迭代（已知环边）

以下环依赖**暂保留函数内 lazy import**（见 `scripts/p3i_hoist_lazy_imports.py` `CYCLE_KEEP`），优先用本目录 Port 替代：

| 环 | 建议 Port | 状态 |
|----|-----------|------|
| `completion_notify` ↔ `outbound_bridge` | `OutboundCompletionHooks` + `completion_policy` | **done** |
| `tool_audit` ↔ `registry` | `ToolRegistryReadPort` | **done** |
| `tool_batch` ↔ `tool_dispatch` | `ToolDispatchPort` + `tool_batch_post_edit` | **done** |
| `health_report` ↔ `health_report_turn` | `HealthDiagnosticPort` + `health_report_input` | **done** |
| `generator` ↔ `acceptance_card` | `report_types` + `generator_schema` | **done** |
| `b9_prod_shaped` ↔ `b9_live_fixed` | `b9_task_fixtures` | **done** |
| `completion_notify` → `report` | 直引（无回边）；`delegate_task_kind` 下沉 L4 | **done** |

新增 Port 模块：

| 模块 | 主要类型 | 服务层 | 典型实现方 |
|------|----------|--------|------------|
| `tool_registry_ports.py` | `ToolRegistryReadPort` | L4 工具 | `tools/registry.py` |
| `tool_registry_registry.py` | `get/set_tool_registry_read` | 横切 | registry 启动注册 |
| `completion_ports.py` | `OutboundCompletionHooks` | L1 出站 | `gateway/completion_notify.py` |
| `completion_registry.py` | `get/set_completion_hooks` | 横切 | completion_notify 注册 |
| `approval_ports.py` | `ApprovalStore` | L7 策略 | `approval_store_impl.py` |
| `approval_registry.py` | `get/set_approval_store` | 横切 | 模块 import 注册 |
| `tool_dispatch_ports.py` | `ToolDispatchPort` | L3 编排 | `core/tool_dispatch.py` |
| `tool_dispatch_registry.py` | `get/set_tool_dispatch` | 横切 | tool_dispatch 启动注册 |
| `health_diagnostic_ports.py` | `HealthDiagnosticPort` | L9 运营 | `ops/health_report_turn.py` |
| `health_diagnostic_registry.py` | `get/set_health_diagnostic` | 横切 | health_report_turn 注册 |

## 依赖规则

- `butler/contracts/**` **不得** import `butler.gateway.*` 具体实现（仅 TYPE_CHECKING 或文档字符串除外）。
- 实现方（gateway、core、tools）可 import contracts；contracts 不 import 实现方。
