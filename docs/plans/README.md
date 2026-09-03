# 规划文档索引

> **文档体系**：[`../DOCUMENTATION.md`](../DOCUMENTATION.md)  
> **提需求 / 边界**：[`decisions/v5-product-boundaries-2026-08.md`](decisions/v5-product-boundaries-2026-08.md)
> **当前路线**：[`active/v5-post-boundary-roadmap-2026-08.md`](active/v5-post-boundary-roadmap-2026-08.md)

## 目录结构

| 子目录 | 内容 |
|--------|------|
| [`active/`](active/) | 活跃产品与 CC 对照；**当前 v5 剩余开发**见 [`v5-remaining-work-2026-08-20.md`](active/v5-remaining-work-2026-08-20.md) |
| [`decisions/`](decisions/) | 否决、边界、Backlog（**决策入口**） |
| [`roadmaps/`](roadmaps/) | 四/五/外部 Agent 已收口路线图（§9/§10 核对） |
| [`comparisons/`](comparisons/) | 竞品对照全文与学习计划（**非待办**） |
| [`corpus/`](corpus/) | 语料与微信测试设计 |
| [`archive/`](archive/) | 已完成实施与历史分析 |

---

## 决策入口

| 文档 | 用途 |
|------|------|
| [`decisions/v5-product-boundaries-2026-08.md`](decisions/v5-product-boundaries-2026-08.md) | v5 硬边界、条件准入、按需立项 |
| [`active/v5-post-boundary-roadmap-2026-08.md`](active/v5-post-boundary-roadmap-2026-08.md) | v5 P0–P4 后续路线 |
| [`archive/v5-ai-guard-migration-checklist-2026-08.md`](archive/v5-ai-guard-migration-checklist-2026-08.md) | 受保护规则的人工作业清单（已归档） |
| [`decisions/roadmap-backlog-and-boundaries-2026-05.md`](decisions/roadmap-backlog-and-boundaries-2026-05.md) | **SUPERSEDED**：v4 历史边界 |
| [`active/v5-followon-projects-2026-08-20.md`](active/v5-followon-projects-2026-08-20.md) | **v5 跟进立项** R8.x.20–22 |
| [`decisions/v5-followons-2026-08-20.md`](decisions/v5-followons-2026-08-20.md) | 四项跟进要/不要 |
| [`decisions/v5-optional-debt-triage-2026-08-20.md`](decisions/v5-optional-debt-triage-2026-08-20.md) | v5 可选债清账（白名单扩容 / 嵌套 architecture 门禁） |
| [`active/extension-rd-loop-2026-06.md`](active/extension-rd-loop-2026-06.md) | 开源/MCP 选型与接入闭环（EXT-1–3 试点） |
| [`decisions/theory-implementation-gap-register-2026-06.md`](decisions/theory-implementation-gap-register-2026-06.md) | 理论—实现差距登记册（G1–G4） |
| [`decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md`](decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md) | Dev 能力上限：对标 CC CLI（非 Cursor） |
| [`decisions/dev-cc-bridge-optional-2026-06.md`](decisions/dev-cc-bridge-optional-2026-06.md) | P3 本机 CC 桥接（暂缓） |
| [`decisions/agent-testing-strategy-2026-06.md`](decisions/agent-testing-strategy-2026-06.md) | Agent/LLM 时代测试分层与断言契约 |
| [`decisions/four-reports-out-of-scope-2026-05.md`](decisions/four-reports-out-of-scope-2026-05.md) | 四报告 18 项否决 |
| [`decisions/five-reports-not-done-2026-05.md`](decisions/five-reports-not-done-2026-05.md) | 五报告 S1–S11 速查 |

---

## 命名对照（易混淆 P0/P2/P3）

| 说法 | 路径 |
|------|------|
| CC 线束 P0–P4 | [`active/cc-butler-gap-analysis-2026-05.md`](active/cc-butler-gap-analysis-2026-05.md) |
| 仓库整理 P0–P3 | [`archive/consolidation-2026-05.md`](archive/consolidation-2026-05.md) |
| 四报告 PR1–PR6 | [`roadmaps/four-reports-improvement-roadmap-2026-05.md`](roadmaps/four-reports-improvement-roadmap-2026-05.md) |
| 五报告 PR-F + P5–P10 | [`roadmaps/five-reports-improvement-roadmap-2026-05.md`](roadmaps/five-reports-improvement-roadmap-2026-05.md) |
| 外部 Agent PR-X | [`roadmaps/external-agent-reports-improvement-roadmap-2026-05.md`](roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) |

能力 env 总表：[`../guides/capabilities-index-2026-05.md`](../guides/capabilities-index-2026-05.md)

---

## 当前状态（2026-06-09）

CC 线束、四/五/外部路线图、外部对标 A/B/C、OpenCode/OpenClaw/OMO、仓库整理 **均已落地**。  
闭环优化 **Phase 0–9** 与 **G1–G4 登记册批次**已收口（核对表见 `post-consolidation-roadmap` **§9** + [`theory-implementation-gap-register-2026-06.md`](decisions/theory-implementation-gap-register-2026-06.md)）；开放项仅 **G1-04** 被动观测。末批真机见 [`projects/LingWen1/docs/pilot-log.md`](../../projects/LingWen1/docs/pilot-log.md)。  
**活跃产品规划**：[`active/post-consolidation-roadmap-2026-05.md`](active/post-consolidation-roadmap-2026-05.md)  
**扩展选型（开源/MCP）**：[`active/extension-rd-loop-2026-06.md`](active/extension-rd-loop-2026-06.md)  
**理论对齐**：[`decisions/theory-implementation-gap-register-2026-06.md`](decisions/theory-implementation-gap-register-2026-06.md)

发版顺序：[`../guides/release-runbook-2026-05.md`](../guides/release-runbook-2026-05.md)

`reference/`（gitignore）由主公维护，不在此索引内。
