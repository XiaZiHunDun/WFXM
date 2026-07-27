# Butler Blackboard — 班次交接系统

> **层级**：横切层 / 黑板系统  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/blackboard/
├── __init__.py                    # 模块初始化
├── state.py                       # 黑板状态
├── shifts/                        # 班次卡目录（实际在 .blackboard/shifts/）
└── （其他黑板模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `state.py` | 黑板状态管理 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
班次开始 → 读取黑板 → 工作 → 写卡 → 班次结束 → 验证黑板
```

## 注意事项

1. **班次交接**：通过 `.blackboard/shifts/` 目录管理班次卡
2. **状态快照**：`.blackboard/state.md` 是当前状态快照
3. **验证机制**：`butler blackboard validate` 验证班次卡
4. **Stop hook**：通过 `BLACKBOARD_STRICT=1` 启用严格模式

## 相关目录

- L9 运营：[`../ops/`](../ops/)
