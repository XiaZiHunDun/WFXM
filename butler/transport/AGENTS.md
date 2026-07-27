# Butler Transport — L6 模型与协议

> **层级**：L6 模型与协议  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/transport/
├── __init__.py                    # 模块初始化
├── base.py                        # LLM 客户端协议
├── llm_client.py                  # LLM 客户端实现
├── fallback.py                    # 降级策略
├── anthropic.py                   # Anthropic 协议
├── chat_completions.py            # Chat Completions 协议
├── types.py                       # 类型定义
└── （其他协议适配）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `base.py` | LLM 客户端协议定义 | 核心模块 |
| `llm_client.py` | LLM 客户端实现 | 核心模块 |
| `fallback.py` | 降级策略 | 可靠性模块 |
| `anthropic.py` | Anthropic API 适配 | 协议适配 |
| `chat_completions.py` | OpenAI 风格 API 适配 | 协议适配 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `LLMClientProtocol` | `base.py` | LLM 客户端协议接口 |
| `LLMClient` | `llm_client.py` | LLM 客户端实现 |
| `create_client_from_entry` | `fallback.py` | 创建带降级的客户端 |

## 数据流

```
AgentLoop → LLMClient → Transport Layer → LLM API
              │                                      │
              └←────────── Response ←────────────────┘
```

## 注意事项

1. **协议抽象**：通过 `LLMClientProtocol` 抽象不同 LLM 提供商
2. **降级策略**：`fallback.py` 实现模型降级和故障转移
3. **协议适配**：各协议适配模块将统一接口转换为具体 API 调用

## 相关目录

- L3 核心：[`../core/`](../core/)
- L6 模型解析：`../model_resolve.py`
