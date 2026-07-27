# Butler Delegate — L2 委派系统

> **层级**：L2 编排与控制 / 委派  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/delegate/
├── __init__.py                    # 模块初始化
├── delegate_registry.py           # 委派注册表
├── delegate_executor.py           # 委派执行器
└── （其他委派模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `delegate_registry.py` | 委派注册表 | 核心模块 |
| `delegate_executor.py` | 委派执行器 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
用户请求 → DelegateRegistry → DelegateExecutor → 委派任务执行
```

## 注意事项

1. **委派深度**：支持多级委派
2. **任务追踪**：通过 `task_orchestrator.py` 追踪委派任务
3. **失败升级**：`ops/delegate_failure_b9_promote.py` 处理委派失败升级

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L4 工具：[`../tools/`](../tools/)
- L9 运营：[`../ops/`](../ops/)
