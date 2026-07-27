# Butler Orchestrator — L2 编排与控制

> **层级**：L2 编排与控制  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/orchestrator/
├── __init__.py                    # 模块初始化
├── loop_factory.py                # AgentLoop 工厂
├── memory_bridge.py               # 记忆桥接
├── skill_bridge.py                # 技能桥接
├── prompt_assembler.py            # 提示词组装器
├── templates/                     # 模板目录
└── （其他辅助模块）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `templates/` | 提示词模板 | 系统提示词模板定义 |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `loop_factory.py` | AgentLoop 工厂 | 核心模块 |
| `memory_bridge.py` | 记忆桥接 | 连接记忆层 |
| `skill_bridge.py` | 技能桥接 | 连接技能层 |
| `prompt_assembler.py` | 提示词组装 | 组装系统提示词 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `AgentLoopFactory` | `loop_factory.py` | 创建 AgentLoop 实例 |
| `MemoryBridge` | `memory_bridge.py` | 记忆注入桥接 |
| `SkillBridge` | `skill_bridge.py` | 技能路由桥接 |

## 数据流

```
用户请求 → Orchestrator
              │
              ├→ prompt_assembler     # 组装提示词
              ├→ memory_bridge       # 注入记忆
              ├→ skill_bridge        # 路由技能
              └→ loop_factory        # 创建并运行 AgentLoop
```

## 注意事项

1. **编排职责**：orchestrator 负责协调各组件，不包含核心对话逻辑
2. **模板系统**：`templates/` 目录包含系统提示词模板
3. **桥接模式**：通过 bridge 模式连接不同层级

## 相关目录

- L1 Gateway：[`../gateway/`](../gateway/)
- L3 核心：[`../core/`](../core/)
- L4 技能：[`../skills/`](../skills/)
- L5 记忆：[`../memory/`](../memory/)
