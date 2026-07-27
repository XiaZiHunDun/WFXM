# Butler Tools — L4 工具与能力

> **层级**：L4 工具与能力  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/tools/
├── __init__.py                    # 模块初始化
├── builtin_register.py            # 内置工具注册
├── builtin_impl.py                # 内置工具实现
├── delegate_impl.py               # 委派工具实现
├── conversation_state_tools.py    # 会话状态工具
├── contacts.py                    # 联系人工具
├── registry.py                    # 工具注册表
├── mcp_self_service.py            # MCP 自助工具
├── project_todos.py               # 项目待办工具
├── path_safety.py                 # 路径安全工具
└── （其他工具实现）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `conversation_state_tools.py` | 会话状态工具 | ~20550 |
| `contacts.py` | 联系人管理工具 | ~18360 |
| `delegate_impl.py` | 委派工具实现 | ~15190 |
| `builtin_register.py` | 内置工具注册 | ~8740 |
| `delegate_report.py` | 委派报告 | ~9250 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `ToolRegistry` | `registry.py` | 工具注册表 |
| `register_builtin_tools` | `builtin_register.py` | 注册内置工具 |
| `delegate_task` | `delegate_impl.py` | 委派任务 |

## 注意事项

1. **工具注册**：所有工具通过 `builtin_register.py` 或 `registry.py` 注册
2. **委派系统**：委派相关工具在 `delegate_impl.py`、`delegate_phases.py`、`delegate_report.py` 中
3. **路径安全**：`path_safety.py` 确保工具操作的路径安全

## 相关目录

- L3 核心：[`../core/`](../core/)
- L4 技能：[`../skills/`](../skills/)
- L4 MCP：[`../mcp/`](../mcp/)
- L4 DevEngine：[`../dev_engine/`](../dev_engine/)
