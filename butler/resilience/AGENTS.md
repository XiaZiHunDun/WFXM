# Butler Resilience — L8 可靠性与韧性

> **层级**：L8 可靠性与韧性  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/resilience/
├── __init__.py                    # 模块初始化（导出所有子模块）
├── message_queue.py               # 消息队列（原 butler/gateway/message_queue.py）
├── message_queue_ops.py           # 消息队列操作（原 butler/gateway/message_queue_ops.py）
├── durable_outbox.py              # 持久化 outbox（原 butler/gateway/durable_outbox.py）
├── inbound_idempotency.py         # 入站幂等性（原 butler/gateway/inbound_idempotency.py）
├── inbound_idempotency_ops.py     # 入站幂等性操作（原 butler/gateway/inbound_idempotency_ops.py）
└── AGENTS.md                      # 本文档
```

## 职责说明

resilience/ 子包统一管理可靠性与韧性相关模块。

## 使用方式

```python
# 推荐方式
from butler.resilience import message_queue, durable_outbox

# 旧方式（仍可用，但会触发 DeprecationWarning）
from butler.gateway import message_queue, durable_outbox
```

## 向后兼容

旧路径的 shim 文件位于 `butler/gateway/` 目录，会自动转发到新位置并发出 DeprecationWarning。

## 数据流

```
入站消息 → inbound_idempotency → message_queue → durable_outbox → 出站
```

## 注意事项

1. **可靠性保障**：这些模块确保消息不丢失、不重复处理
2. **持久化**：`durable_outbox` 确保出站消息持久化

## 相关目录

- L1 Gateway：[`../gateway/`](../gateway/)
- L9 运营：[`../ops/`](../ops/)
