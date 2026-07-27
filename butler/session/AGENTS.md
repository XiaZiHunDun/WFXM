# Butler Session — 会话管理

> **层级**：跨层级 / 会话管理  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/session/
├── __init__.py                    # 模块初始化
├── new_session.py                 # 新会话创建
├── session_context.py             # 会话上下文
└── （其他会话模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `new_session.py` | 新会话创建 | 核心模块 |
| `session_context.py` | 会话上下文管理 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
新会话请求 → new_session → session_context → AgentLoop
```

## 注意事项

1. **会话生命周期**：由 `gateway/session_registry.py` 管理
2. **会话状态**：核心会话状态在 `core/conversation_state.py` 中
3. **会话记忆**：会话级记忆在 `core/session_transcript.py` 中

## 相关目录

- L1 Gateway：[`../gateway/`](../gateway/)
- L3 核心：[`../core/`](../core/)
