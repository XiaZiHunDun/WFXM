# Butler Workflows — L2 工作流系统

> **层级**：L2 编排与控制 / 工作流  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/workflows/
├── __init__.py                    # 模块初始化
├── step_runner.py                 # 步骤运行器（原 butler/workflow_step_runner.py）
├── runner.py                      # 工作流执行器
├── runner_ops.py                  # 执行器操作
├── loader.py                      # 工作流加载器
├── schema.py                      # 工作流 schema
├── callbacks.py                   # 回调处理
├── pause_state.py                 # 暂停状态
├── artifact_paths.py              # 产物路径
├── validate.py                    # 验证
├── until_assert.py                # 断言等待
├── variables.py                   # 变量管理
├── workflow_run_snapshot.py       # 运行快照
├── builtin/                       # 内置工作流
└── AGENTS.md                      # 本文档
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `runner.py` | 工作流执行器 | ~18740 |
| `loader.py` | 工作流加载器 | ~10600 |
| `step_runner.py` | 步骤运行器 | ~3770 |
| `rules.py` | 工作流规则 | ~6250 |

## 使用方式

```python
# 推荐方式
from butler.workflows import step_runner, runner

# 旧方式（仍可用，但会触发 DeprecationWarning）
from butler import workflow_step_runner
```

## 向后兼容

旧路径的 shim 文件位于 `butler/` 顶层目录，会自动转发到新位置并发出 DeprecationWarning。

## 数据流

```
用户请求 → WorkflowLoader → WorkflowRunner → 步骤执行
```

## 注意事项

1. **工作流门控**：通过 `permissions/human_gate.py` 提供工作流门控功能
2. **自动续跑**：通过 `BUTLER_WORKFLOW_AUTO_RESUME=1` 启用

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L7 权限：[`../permissions/`](../permissions/)
