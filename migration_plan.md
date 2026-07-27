# 目录重构迁移计划

> **目标**：将分散在顶层的模块迁移到对应的子包，创建清晰的目录结构  
> **策略**：兼容层优先 — 先创建 shim 文件，再迁移代码，最后删除旧文件  
> **日期**：2026-07-17

## 迁移映射表

### 1. configuration/ 子包（配置模块）

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `butler/config.py` | `butler/configuration/settings.py` | 待迁移 |
| `butler/config_ops.py` | `butler/configuration/settings_ops.py` | 待迁移 |
| `butler/gateway_settings.py` | `butler/configuration/gateway.py` | 待迁移 |
| `butler/gateway_settings_ops.py` | `butler/configuration/gateway_ops.py` | 待迁移 |
| `butler/memory_settings.py` | `butler/configuration/memory.py` | 待迁移 |
| `butler/context_settings.py` | `butler/configuration/context.py` | 待迁移 |
| `butler/config_secrets.py` | `butler/configuration/secrets.py` | 待迁移 |
| `butler/config_secrets_ops.py` | `butler/configuration/secrets_ops.py` | 待迁移 |
| `butler/config_secrets_crypto.py` | `butler/configuration/secrets_crypto.py` | 待迁移 |
| `butler/config_secrets_crypto_ops.py` | `butler/configuration/secrets_crypto_ops.py` | 待迁移 |
| `butler/config_service.py` | `butler/configuration/service.py` | 待迁移 |
| `butler/provider_presets.py` | `butler/configuration/provider_presets.py` | 待迁移 |

### 2. utilities/ 子包（工具模块）

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `butler/env_parse.py` | `butler/utilities/env_parse.py` | 待迁移 |
| `butler/logging_config.py` | `butler/utilities/logging_config.py` | 待迁移 |
| `butler/tenant.py` | `butler/utilities/tenant.py` | 待迁移 |
| `butler/repo_paths.py` | `butler/utilities/repo_paths.py` | 待迁移 |

### 3. resilience/ 子包（可靠性模块）

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `butler/gateway/message_queue.py` | `butler/resilience/message_queue.py` | 待迁移 |
| `butler/gateway/durable_outbox.py` | `butler/resilience/durable_outbox.py` | 待迁移 |
| `butler/gateway/inbound_idempotency.py` | `butler/resilience/inbound_idempotency.py` | 待迁移 |

### 4. permissions/ 子包（权限模块）

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `butler/human_gate.py` | `butler/permissions/human_gate.py` | 待迁移 |
| `butler/human_gate_ops.py` | `butler/permissions/human_gate_ops.py` | 待迁移 |

### 5. workflows/ 子包（工作流模块）

| 旧路径 | 新路径 | 状态 |
|--------|--------|------|
| `butler/workflow_step_runner.py` | `butler/workflows/step_runner.py` | 待迁移 |

## 兼容策略

### 阶段 1：创建 shim 文件（立即执行）

在旧路径创建 shim 文件，转发到新路径：

```python
# butler/config.py（shim）
from butler.configuration.settings import *

import warnings
warnings.warn(
    "butler.config is deprecated, use butler.configuration.settings instead",
    DeprecationWarning,
    stacklevel=2
)
```

### 阶段 2：迁移代码（分批执行）

按模块分批迁移代码到新位置，更新内部导入。

### 阶段 3：全仓替换导入路径（逐步执行）

使用 grep 查找所有旧路径的引用，逐步替换为新路径。

### 阶段 4：删除 shim 文件（最后执行）

确认所有引用已替换后，删除 shim 文件。

## 执行顺序

1. 先迁移 configuration/（核心配置，影响最广）
2. 再迁移 utilities/（工具模块，依赖较少）
3. 然后迁移 resilience/（可靠性模块，需要修改 gateway 导入）
4. 接着迁移 permissions/（权限模块）
5. 最后迁移 workflows/（工作流模块）

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 导入错误 | 高 | 创建 shim 文件提供向后兼容 |
| 循环依赖 | 中 | 使用 `__getattr__` 延迟导入 |
| 测试失败 | 中 | 每批迁移后运行测试门禁 |
| 配置加载失败 | 高 | 先验证配置模块的迁移 |

## 验证步骤

每批迁移后执行：

```bash
# 快速门禁
./scripts/butler-pytest-fast-gate.sh

# mypy 检查
bash scripts/butler-mypy-strict-gate.sh

# 层依赖检查
bash scripts/butler-layer-import-gate.sh
```
