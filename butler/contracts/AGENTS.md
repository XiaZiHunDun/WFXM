# Butler Contracts — 横切契约层

> **层级**：横切层 / 契约  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/contracts/
├── __init__.py                    # 模块初始化
├── README.md                      # 契约说明文档
├── port_definitions.py            # 端口定义
└── （其他契约模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `README.md` | 契约说明文档 | 核心文档 |
| `port_definitions.py` | 端口定义 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
模块间通信 → 契约接口 → 端口定义 → 类型安全
```

## 注意事项

1. **契约 SSOT**：`contracts/README.md` 是契约的权威说明
2. **端口定义**：通过 `port_definitions.py` 定义模块间的接口
3. **类型安全**：契约确保模块间通信的类型安全

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L3 核心：[`../core/`](../core/)
