# 规划文档索引

> 更新：2026-05-25 | 区分 **CC 线束**、**仓库整理**、**外部对标** 三套「P0/P2/P3」命名，勿混用。

## 命名对照（易混淆）

| 说法 | 文档 | 含义 |
|------|------|------|
| **CC 线束 P0–P4** | [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md) | Claude Code 源码对照；Loop/Gateway 能力（压缩、队列、P3/P4 §11） |
| **仓库整理 P0–P2** | [`consolidation-2026-05.md`](consolidation-2026-05.md) | 目录瘦身、文档归档、死代码清理前置 |
| **仓库整理 P3** | [`consolidation-p3-implementation-2026-05.md`](consolidation-p3-implementation-2026-05.md) | 实现层熵减（与 CC P3 无关） |
| **外部对标 P0–P2** | [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md) | Prometheus/OpenClaw/Dify **设计借鉴**（已收口，零依赖） |
| **OpenCode 对标 P0–P1** | [`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md) | 压缩/prune/权限/doom loop/委派/指令 walk-up（**已落地**） |
| **MCP 薄客户端 P3** | [`butler-mcp-capability-2026-05.md`](butler-mcp-capability-2026-05.md) | stdio/HTTP Client + `butler mcp serve`（**已落地**） |

## 当前状态（2026-05-25）

| 类别 | 状态 |
|------|------|
| CC 线束 §4–§11 | 已落地 main（见 gap 文档 §3 核验） |
| 仓库整理 | P0–P3 已完成 |
| 外部对标 | P0–P2 已落地；**无后续必做项**（不做队列 jsonl WAL、自动续跑 workflow、多实例 MQ） |
| OpenCode 对标 | P0–P2 已落地（SQLite 全量模型仍暂缓） |
| MCP P3 | 薄 Client + 诊断 + `butler mcp serve`（默认关闭） |
| 产品后续 | [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) |

## 活跃参考

| 文档 | 用途 |
|------|------|
| [`cc-butler-gap-analysis-2026-05.md`](cc-butler-gap-analysis-2026-05.md) | 改 Loop/Gateway 前先看对照与落地状态 |
| [`post-consolidation-roadmap-2026-05.md`](post-consolidation-roadmap-2026-05.md) | 灵文运营、多项目、语料 |
| [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md) | 外部项目学习记录（**已关闭**） |
| [`opencode-learning-plan-2026-05.md`](opencode-learning-plan-2026-05.md) | OpenCode 对标（**已落地 P0–P1**） |
| [`butler-mcp-capability-2026-05.md`](butler-mcp-capability-2026-05.md) | MCP 薄客户端（**已落地**） |

## 归档 / 专项（按需打开）

| 文档 | 说明 |
|------|------|
| [`consolidation-2026-05.md`](consolidation-2026-05.md) | 整理方案全文 |
| [`memory-unification-implementation-2026-05.md`](memory-unification-implementation-2026-05.md) | 记忆双轨合并 |
| [`wechat-steer-implementation-2026-05.md`](wechat-steer-implementation-2026-05.md) | `/steer` 实现 |
| [`corpus-testing-module-design-2026-05.md`](corpus-testing-module-design-2026-05.md) | 语料测试模块 |
| [`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md) | 双实例 / 记忆排查备忘 |

`reference/` 目录（gitignore）由主公维护，**不在此索引内**。
