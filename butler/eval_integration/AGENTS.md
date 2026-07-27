# Butler Eval Integration — L9 评估集成

> **层级**：L9 观测与运营 / 评估  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/eval_integration/
├── __init__.py                    # 模块初始化
├── eval_harness.py                # 评估线束
└── （其他评估模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `eval_harness.py` | 评估线束 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
评估请求 → eval_harness → 执行评估 → 生成报告
```

## 注意事项

1. **评估线束**：`eval_harness.py` 是评估系统的核心
2. **评估门禁**：通过 `butler eval` 命令触发评估
3. **测试支持**：支持 smoke quick、full 评估等

## 相关目录

- L9 运营：[`../ops/`](../ops/)
