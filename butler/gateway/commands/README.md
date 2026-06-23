# Gateway 斜杠命令（单轨）

> **2026-06-23**：实现与注册统一在 `butler/gateway/commands/`；根目录 `*_commands.py` 已移除。

| 文件模式 | 职责 |
|----------|------|
| `*_commands.py` | `CommandDef` 注册 + registry handler（`dispatch` 入口） |
| `*_handlers.py` | 命令业务逻辑（git/测试/项目/MCP/registry 等） |
| `command_registry.py` | `dispatch()`、`require_owner()`、默认命令元数据 |

导入 `butler.gateway.commands` 时各子模块自动 `register()`。外部调用方应使用 `butler.gateway.commands.<domain>_handlers`，勿再引用已删除的 `butler.gateway.<domain>_commands`。
