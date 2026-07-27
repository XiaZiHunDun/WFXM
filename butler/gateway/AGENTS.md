# Butler Gateway — L1 接入与交互

> **层级**：L1 接入与交互  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/gateway/
├── __init__.py                    # 模块初始化
├── commands/                      # 命令定义
├── platforms/                     # 平台适配（微信等）
├── message_handler.py             # 消息处理器（主入口）
├── message_queue.py               # 消息队列
├── message_pipelines.py           # 消息处理管线
├── session_registry.py            # 会话注册表
├── outbound_bridge.py             # 出站桥接
├── runner.py                      # 运行器
├── locked_phases.py               # 门禁阶段
├── durable_outbox.py              # 持久化 outbox
├── completion_notify.py           # 完成通知
├── owner_surface.py               # 主人界面
├── wechat_scenario_sim.py         # 微信场景模拟
└── （其他辅助模块）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `commands/` | 命令定义 | 各命令的实现（如 /简报、/委派、/诊断等） |
| `platforms/` | 平台适配 | 微信等平台的适配层 |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `message_handler.py` | 消息处理主入口 | ~11850 |
| `message_queue.py` | 消息队列实现 | ~15360 |
| `message_pipelines.py` | 消息处理管线 | ~17800 |
| `outbound_bridge.py` | 出站消息桥接 | ~25110 |
| `locked_phases.py` | 门禁阶段管理 | ~29130 |
| `session_registry.py` | 会话生命周期管理 | ~12350 |
| `wechat_scenario_sim.py` | 微信场景模拟 | ~27670 |
| `handler_helpers.py` | 处理器辅助函数 | ~20420 |
| `completion_notify.py` | 完成通知系统 | ~16160 |
| `runner.py` | 任务运行器 | ~11360 |
| `owner_surface.py` | 主人界面 | ~11850 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `ButlerMessageHandler` | `message_handler.py` | 消息处理主类 |
| `MessageQueue` | `message_queue.py` | 消息队列管理 |
| `SessionRegistry` | `session_registry.py` | 会话注册表 |
| `OutboundBridge` | `outbound_bridge.py` | 出站桥接 |

## 数据流

```
微信消息 → ButlerMessageHandler
              │
              ├→ inbound_pipeline()    # 入站处理
              ├→ message_queue         # 入队
              ├→ SessionRegistry       # 会话管理
              ├→ AgentLoop             # 调用核心循环
              └→ outbound_bridge       # 出站发送
```

## 注意事项

1. **职责范围**：gateway 负责微信消息的接收、处理、发送，不包含核心对话逻辑
2. **门禁系统**：`locked_phases.py` 是门禁阶段的核心实现，控制任务执行流程
3. **可靠性**：`durable_outbox.py` 和 `inbound_idempotency.py` 保证消息可靠性
4. **测试模拟**：`wechat_scenario_sim.py` 用于测试场景模拟

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L3 核心：[`../core/`](../core/)
- L8 可靠性：[`../resilience/`](../resilience/)
