# Butler Training — 训练模块

> **层级**：L9 观测与运营 / 训练  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/training/
├── __init__.py                    # 模块初始化
├── training_corpus.py             # 训练语料
└── （其他训练模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `training_corpus.py` | 训练语料管理 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
语料收集 → training_corpus → 训练数据 → 模型训练
```

## 注意事项

1. **语料管理**：管理训练所需的语料数据
2. **数据质量**：确保训练数据的质量

## 相关目录

- L5 记忆：[`../memory/`](../memory/)
- L9 运营：[`../ops/`](../ops/)
