# Butler Configuration — 横切配置模块

> **层级**：横切层 / 配置管理  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/configuration/
├── __init__.py                    # 模块初始化（导出所有子模块）
├── settings.py                    # 核心配置（原 butler/config.py）
├── settings_ops.py                # 核心配置操作（原 butler/config_ops.py）
├── gateway.py                     # Gateway 配置（原 butler/gateway_settings.py）
├── gateway_ops.py                 # Gateway 配置操作（原 butler/gateway_settings_ops.py）
├── memory.py                      # 记忆配置（原 butler/memory_settings.py）
├── context.py                     # 上下文配置（原 butler/context_settings.py）
├── secrets.py                     # 密钥配置（原 butler/config_secrets.py）
├── secrets_ops.py                 # 密钥配置操作（原 butler/config_secrets_ops.py）
├── secrets_crypto.py              # 密钥加密（原 butler/config_secrets_crypto.py）
├── secrets_crypto_ops.py          # 密钥加密操作（原 butler/config_secrets_crypto_ops.py）
├── service.py                     # 服务配置（原 butler/config_service.py）
├── provider_presets.py            # 提供商预设（原 butler/provider_presets.py）
└── AGENTS.md                      # 本文档
```

## 职责说明

configuration/ 子包统一管理项目所有配置模块。

## 使用方式

```python
# 推荐方式
from butler.configuration import settings, secrets, gateway

# 旧方式（仍可用，但会触发 DeprecationWarning）
from butler import config, config_secrets, gateway_settings
```

## 向后兼容

旧路径的 shim 文件位于 `butler/` 顶层目录，会自动转发到新位置并发出 DeprecationWarning。

## 注意事项

1. **循环依赖**：避免在配置模块中导入 `butler.configuration` 子包
2. **配置加载**：通过 `get_butler_settings()` 加载配置

## 相关目录

- L9 运营：[`../ops/`](../ops/)
- 工具模块：[`../utilities/`](../utilities/)
