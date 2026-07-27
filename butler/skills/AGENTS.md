# Butler Skills — L4 技能系统

> **层级**：L4 工具与能力 / 技能系统  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/skills/
├── __init__.py                    # 模块初始化
├── manager.py                     # 技能管理器
├── injection_policy.py            # 技能注入策略
├── skill_registry.py              # 技能注册表
├── （其他技能模块）
```

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `manager.py` | 技能管理器 | ~7110 |
| `injection_policy.py` | 技能注入策略 | 核心模块 |
| `skill_registry.py` | 技能注册表 | 核心模块 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `SkillManager` | `manager.py` | 技能管理主类 |
| `SkillRegistry` | `skill_registry.py` | 技能注册表 |

## 数据流

```
会话 → SkillManager → 技能匹配 → 技能注入 → AgentLoop
```

## 注意事项

1. **技能自动合并**：系统自动合并用户配置的技能
2. **注入策略**：`injection_policy.py` 控制技能如何注入到对话中
3. **路由桥接**：`core/skill_tool_bridge.py` 提供技能与工具的桥接

## 相关目录

- L2 编排：[`../orchestrator/`](../orchestrator/)
- L3 核心：[`../core/`](../core/)
- L4 工具：[`../tools/`](../tools/)
