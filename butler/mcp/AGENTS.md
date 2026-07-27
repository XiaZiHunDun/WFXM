# Butler MCP — L4 MCP 工具

> **层级**：L4 工具与能力 / MCP 工具  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/mcp/
├── __init__.py                    # 模块初始化
├── mcp_host.py                    # MCP 主机
├── mcp_client.py                  # MCP 客户端
├── mcp_self_service.py            # MCP 自助服务
└── （其他 MCP 模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `mcp_host.py` | MCP 主机实现 | 核心模块 |
| `mcp_client.py` | MCP 客户端实现 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
AgentLoop → MCP Client → MCP Host → MCP 工具执行
```

## 注意事项

1. **可选功能**：MCP 功能通过 `BUTLER_MCP_ENABLED=1` 启用
2. **自助服务**：`tools/mcp_self_service.py` 提供 MCP 自助工具
3. **能力边界**：不做全量 MCP Host，仅支持部分 MCP 工具

## 相关目录

- L4 工具：[`../tools/`](../tools/)
- L3 核心：[`../core/`](../core/)
