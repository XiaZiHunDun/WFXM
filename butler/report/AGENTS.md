# Butler Report — L9 报告系统

> **层级**：L9 观测与运营 / 报告  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/report/
├── __init__.py                    # 模块初始化
├── report_pipeline.py             # 报告管线
└── （其他报告模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `report_pipeline.py` | 报告管线 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
数据收集 → report_pipeline → 结构化报告 → 用户展示
```

## 注意事项

1. **结构化报告**：生成结构化报告供用户查看
2. **渐进披露**：支持报告的渐进披露

## 相关目录

- L3 核心：[`../core/`](../core/)
- L9 运营：[`../ops/`](../ops/)
