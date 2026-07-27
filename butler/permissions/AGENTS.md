# Butler Permissions — L7 策略与门控

> **层级**：L7 策略与门控  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/permissions/
├── __init__.py                    # 模块初始化
├── policies.py                    # 权限策略
├── human_gate.py                  # 人工门控（原 butler/human_gate.py）
├── human_gate_ops.py              # 人工门控操作（原 butler/human_gate_ops.py）
├── rules.py                       # 权限规则
├── rules_context.py               # 规则上下文
├── approvals.py                   # 审批流程
├── doom_loop.py                   # 厄运循环检测
├── tool_boundary_registry.py      # 工具边界注册表
└── AGENTS.md                      # 本文档
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `human_gate.py` | 人工门控 | ~12010 |
| `rules.py` | 权限规则 | ~16170 |
| `approvals.py` | 审批流程 | ~11360 |
| `tool_boundary_registry.py` | 工具边界 | ~7800 |

## 使用方式

```python
# 推荐方式
from butler.permissions import human_gate, rules

# 旧方式（仍可用，但会触发 DeprecationWarning）
from butler import human_gate
```

## 向后兼容

旧路径的 shim 文件位于 `butler/` 顶层目录，会自动转发到新位置并发出 DeprecationWarning。

## 数据流

```
用户请求 → 权限检查 → 允许/拒绝/询问
```

## 注意事项

1. **权限配置**：通过 `.butler/permissions.yaml` 配置权限规则
2. **门控系统**：`human_gate.py` 提供人工门控功能
3. **策略定义**：`rules.py` 和 `policies.py` 定义权限策略

## 相关目录

- L4 工具：[`../tools/`](../tools/)
