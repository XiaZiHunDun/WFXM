# ADR：EventsSink 单注册合并（ACL 续）

> **状态**：已采纳（2026-06-29）  
> **边界**：`butler/contracts` ↔ `butler/core` ↔ `butler/gateway`  
> **关联**：[`compaction-acl-adr-2026-07.md`](compaction-acl-adr-2026-07.md) · ENG-6

## 背景

历史上存在两套 EventsSink：

1. `butler/contracts/events.py` — transcript（`record_generic_event` / `record_tool_action`）
2. `butler/core/events_sink.py` — compaction hooks + urgent inbound

`GatewayEventsSink` 同时实现两类方法，但曾分别注册到 contracts 与 core 两套全局表，测试与启动顺序可能导致行为不一致。

## 决策

1. **统一 Protocol**：`butler/contracts/events.py` 包含全部 5 组方法 + `UrgentInbound` + `NullEventsSink`
2. **单注册表**：`butler/contracts/sink_registry.py` 为 SSOT；`get_events_sink()` 永不返回 `None`
3. **Core 薄垫片**：`butler/core/events_sink.py` 仅 re-export + 委托 shims（`invoke_hook` 等）
4. **Gateway 单点安装**：`install_gateway_events_sink()` → `contracts.sink_registry.set_events_sink`

## 非目标

- 将 transcript 写入迁出 `session_transcript` 模块
- 多 sink 组合（CompositeEventsSink）— 暂不需要

## 验收

- `tests/test_contracts_events.py` 绿（含 core/contracts 同注册表断言）
- `tests/test_core_events_sink_layering.py` 绿
- Gateway 启动后 compaction shims 与 transcript 共用同一 `GatewayEventsSink` 实例
