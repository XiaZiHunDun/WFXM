# Butler CLI — L1 命令行接口

> **层级**：L1 接入与交互 / CLI  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/cli/
├── __init__.py                    # 模块初始化
├── commands/                      # CLI 命令
├── main.py                        # CLI 主入口（在顶层）
└── （其他 CLI 模块）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `commands/` | CLI 命令定义 | 各 CLI 命令的实现 |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `main.py` | CLI 主入口 | ~5980（顶层目录） |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| （待补充） | （待补充） | （待补充） |

## 数据流

```
命令行 → main.py → CLI 命令 → 对应功能模块
```

## 注意事项

1. **CLI 入口**：`butler/main.py` 是 CLI 的主入口
2. **命令注册**：通过 `commands/` 目录下的模块注册各命令
3. **快速命令**：支持 `butler onboard`、`butler eval`、`butler blackboard` 等

## 相关目录

- L1 Gateway：[`../gateway/`](../gateway/)
