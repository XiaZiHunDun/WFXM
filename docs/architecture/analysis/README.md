# Butler v4 理论分析文档包（2026-06 / 2026-07 补丁）

> **用途**：供高级模型对 Butler 的**建模、形式化推导、工程蓝图、解耦评估**进行独立审阅、批判与扩展。  
> **生成**：2026-06-12 初版；**2026-07-08** 增九层映射与复验包。  
> **勿作实现依据**：改代码仍以 [`../v4-architecture.md`](../v4-architecture.md) + [`../v4-layer-model.md`](../v4-layer-model.md) 与测试为准。

## 文档清单

| 文档 | 路径 | 内容 |
|------|------|------|
| **层映射 SSOT** | [`../layer-theory-engineering-map.md`](../layer-theory-engineering-map.md) | 理论七层 ↔ 工程九层 ↔ 代码 ↔ 定理索引 |
| **建模** | [`modeling-2026-06.md`](modeling-2026-06.md) | 概念实体、三元张力、七层产品模型（+ §九层对照补丁） |
| **形式化推导** | [`formal-theory-2026-06.md`](formal-theory-2026-06.md) | 定义、不变量、主/子理论定理、前提验证（2026-06 快照） |
| **形式化复验** | [`formal-theory-2026-07.md`](formal-theory-2026-07.md) | **2026-07** 竖切后前提复验矩阵（T1–T10 / MT / CT） |
| **解耦评估** | [`decoupling-assessment-2026-07.md`](decoupling-assessment-2026-07.md) | ENG-15 首跑、allowlist、剩余耦合 |
| **蓝图** | [`blueprint-2026-06.md`](blueprint-2026-06.md) | 模块职责、数据流（+ §九层工程映射补丁） |

> **已 superseded 作 SSOT**：blueprint §1 原「六层工程图」— 实现分层以 [`v4-layer-model.md`](../v4-layer-model.md) 为准。

## 理论 SSOT（原文，本包为摘要索引）

| 文档 | 版本 |
|------|------|
| [`../v4-theoretical-baseline.md`](../v4-theoretical-baseline.md) | v3.1.2 |
| [`../v4-detailed-design.md`](../v4-detailed-design.md) | v2.2 |
| [`../v4-memory-theory.md`](../v4-memory-theory.md) | v1.2（工程 L5） |
| [`../v4-dev-engine-theory.md`](../v4-dev-engine-theory.md) | v1.5（工程 L4） |
| [`../../plans/decisions/theory-implementation-gap-register-2026-06.md`](../../plans/decisions/theory-implementation-gap-register-2026-06.md) | G1–G4 登记册 |

## 建议审阅顺序

1. **层映射** → 理解理论七层与工程九层如何对应  
2. **建模** → 系统是什么、矛盾与公理从何而来  
3. **形式化复验 2026-07** → 竖切后前提是否仍锚定正确模块  
4. **形式化推导 2026-06** → 完整定理链与诚实边界  
5. **解耦评估** → ENG-15 与 Port 封装现状  
6. **蓝图** → 对照代码模块与 Backlog
