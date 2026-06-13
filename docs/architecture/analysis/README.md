# Butler v4 理论分析文档包（2026-06）

> **用途**：供高级模型对 Butler 的**建模、形式化推导、工程蓝图**进行独立审阅、批判与扩展。  
> **生成**：2026-06-12，基于代码 + 理论 SSOT 整理，非替代原文。  
> **勿作实现依据**：改代码仍以 [`../v4-architecture.md`](../v4-architecture.md) 与测试为准。

## 文档清单

| 文档 | 路径 | 内容 |
|------|------|------|
| **建模** | [`modeling-2026-06.md`](modeling-2026-06.md) | 概念实体、三元张力、七层模型、状态/通道/记忆/权限概念模型 |
| **形式化理论推导** | [`formal-theory-2026-06.md`](formal-theory-2026-06.md) | 定义、不变量、主/子理论定理、前提验证、坚实度、差距登记 |
| **蓝图** | [`blueprint-2026-06.md`](blueprint-2026-06.md) | 六层工程映射、模块职责、数据流、配置面、实现状态、演进轨道 |

## 理论 SSOT（原文，本包为摘要索引）

| 文档 | 版本 |
|------|------|
| [`../v4-theoretical-baseline.md`](../v4-theoretical-baseline.md) | v3.1.1 |
| [`../v4-detailed-design.md`](../v4-detailed-design.md) | v2.2 |
| [`../v4-memory-theory.md`](../v4-memory-theory.md) | v1.2 |
| [`../v4-dev-engine-theory.md`](../v4-dev-engine-theory.md) | v1.5 |
| [`../../plans/decisions/theory-implementation-gap-register-2026-06.md`](../../plans/decisions/theory-implementation-gap-register-2026-06.md) | G1–G4 登记册 |

## 建议审阅顺序

1. **建模** → 理解系统是什么、矛盾与公理从何而来  
2. **形式化推导** → 检验定理链、前提与诚实边界  
3. **蓝图** → 对照代码模块与未落地/Backlog 项
