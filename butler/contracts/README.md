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

| 环 | 建议 Port |
|----|-----------|
| `completion_notify` ↔ `outbound_bridge` | 扩展 `BridgeAccess` |
| `tool_audit` ↔ `registry` | 工具结果/注册表只读 Port |
| `tool_batch` ↔ `tool_dispatch` | 分发 Port（单入口 `dispatch_one_tool`） |
| `health_report` ↔ `health_report_turn` | 诊断行 Provider Port |

## 依赖规则

- `butler/contracts/**` **不得** import `butler.gateway.*` 具体实现（仅 TYPE_CHECKING 或文档字符串除外）。
- 实现方（gateway、core、tools）可 import contracts；contracts 不 import 实现方。
