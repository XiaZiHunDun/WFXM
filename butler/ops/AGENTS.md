# Butler Ops — L9 观测与运营

> **层级**：L9 观测与运营  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/ops/
├── __init__.py                    # 模块初始化
├── runtime_metrics.py             # 运行指标
├── butler_inbox.py                # 管家简报/Inbox
├── owner_quality_surface.py       # 主人质量面
├── owner_trust_surface.py         # 信任主人面
├── degradation_registry.py        # 降级注册表
├── langfuse_tracker.py            # Langfuse 追踪
├── delegate_failure_b9_promote.py # B9 委派失败升级
└── （其他运营模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `runtime_metrics.py` | 运行时指标收集 | 核心模块 |
| `butler_inbox.py` | 简报/Inbox 汇总 | 用户界面 |
| `owner_quality_surface.py` | 质量面展示 | 用户界面 |
| `owner_trust_surface.py` | 信任面展示 | 用户界面 |
| `degradation_registry.py` | 降级注册 | 可靠性 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `RuntimeMetrics` | `runtime_metrics.py` | 运行指标收集器 |
| `ButlerInbox` | `butler_inbox.py` | 简报系统 |

## 数据流

```
各模块 → RuntimeMetrics → 指标存储 → /诊断 /简报
              │                                   │
              └──→ degradation_registry ←─────────┘
```

## 注意事项

1. **观测职责**：ops 模块负责收集和展示运行指标
2. **用户界面**：`butler_inbox.py`、`owner_quality_surface.py`、`owner_trust_surface.py` 提供用户可见的运营界面
3. **降级管理**：`degradation_registry.py` 管理系统降级状态

## 相关目录

- L3 核心：[`../core/`](../core/)
- L8 可靠性：[`../resilience/`](../resilience/)
