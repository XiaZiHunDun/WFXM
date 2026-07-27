# Butler Utilities — 横切工具模块

> **层级**：横切层 / 工具函数  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/utilities/
├── __init__.py                    # 模块初始化（导出所有子模块）
├── env_parse.py                   # 环境变量解析（原 butler/env_parse.py）
├── logging_config.py              # 日志配置（原 butler/logging_config.py）
├── tenant.py                      # 租户管理（原 butler/tenant.py）
├── repo_paths.py                  # 仓库路径（原 butler/repo_paths.py）
└── AGENTS.md                      # 本文档
```

## 职责说明

utilities/ 子包统一管理项目通用工具函数。

## 使用方式

```python
# 推荐方式
from butler.utilities import tenant, env_parse

# 旧方式（仍可用，但会触发 DeprecationWarning）
from butler import tenant, env_parse
```

## 向后兼容

旧路径的 shim 文件位于 `butler/` 顶层目录，会自动转发到新位置并发出 DeprecationWarning。

## 注意事项

1. **通用工具**：这些是项目通用的工具函数，不依赖特定业务逻辑

## 相关目录

- 配置模块：[`../configuration/`](../configuration/)
