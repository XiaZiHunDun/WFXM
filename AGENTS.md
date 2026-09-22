# Cursor / Agent 工作说明（WFXM / Butler v5）

> **Butler v5 是唯一活动产品主线；`butler/` v4 已退役。** 新会话不要用 v4 文档、`docs/history/` 或训练记忆推断 v5 实现。
> **新会话开篇前 30 秒**：读 [`.blackboard/state.md`](.blackboard/state.md) → 本文件 → 撞点按 §3 流程。

## §1 必读表（7 条）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | [`butler-v5/DESIGN.md`](butler-v5/DESIGN.md) | 改目标架构、概念、数据、安全或扩展边界 |
| 2 | [`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md) | 查当前生产 Loop / Gateway / 工具 / 数据 / 调用链 |
| 3 | [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) | 视觉架构图（Mermaid 4 张） |
| 4 | [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](docs/plans/decisions/v5-product-boundaries-2026-08.md) | 提需求 / 否决 / 条件准入 / 立项 |
| 5 | [`docs/plans/active/ROADMAP.md`](docs/plans/active/ROADMAP.md) | D-series 累计（117 ship）+ 维度 2/3/4 候选 |
| 6 | [`docs/FAQ.md`](docs/FAQ.md) | owner 视角 FAQ（D-series / audit-driven / 节奏判据） |
| 7 | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) | v5 代码约束 + 包边界 + 测试 |
| 8 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层与维护规则 |

## §2 v5 事实规则（5 条硬约束）

1. **生产路径**: `butler-v5/cli + apps/api → packages/runtime → adapters/persistence`
2. **目标 vs 实现**: `butler-v5/DESIGN.md`（目标架构）/ `v5-production-architecture`（当前事实）必须分开描述
3. **`_archive/packages/{application,infrastructure}`** 未接入生产；不得用其单测声称能力已交付
4. **生产 DB schema**: 只认 [`packages/persistence/src/migrations/0001_initial.sql`](butler-v5/packages/persistence/src/migrations/0001_initial.sql)
5. **新入口归一化**: Run Trigger →（Policy Ask 时 `waiting_approval`）→（需要时 ScopedGrant）→ Provider Boundary → Audit；模型调用不走副作用咽喉
6. **§20 KNOWN_ENTRY_POINTS**（D77 T5 强化）: 分 LLM + Non-LLM 2-tier；`/health` 等 non-LLM entry 不走模型路径
7. **MCP / 浏览器 / UI / 多 Channel / 调度 = 条件准入**（per DESIGN §7.1），非默认能力，非整类否决

## §3 撞点流程（5 步）

1. **owner 撞点** → 查 [`MEMORY.md`](.blackboard/MEMORY.md) "Recent Sessions" 找最近 cycle memo
2. **看 raw findings**: `.audit/Dxx/raw-findings.json`
3. **ship 模板**: `ship Dxx Tn <findings-id> <files>`（per D77 7-ship 模式）
4. **pause 模板**: `pause Dxx`（落 MEMORY.md + `project-pause-state-*.md`）
5. **audit 模板**: `audit Dxx`（cycle 24+）

## §4 v4 legacy 兼容层

`docs/architecture/v5-r10-handoff.md` §6 / `.cursorrules` / hooks 表 / pre-commit 仍含 v4 保护项，作为 v4 兼容层保留：

- 继续遵守保护，不得擅自移除
- 但**不是** v5 产品架构或能力现状的事实来源
- 修改 AI 守卫 / `.claude/settings.json` / 受保护文件仍需人工操作（含 `[MANUAL-OVERRIDE]` 提交流程）

**D1 已执行（2026-08-25）**: `~/.butler/` 已删除；回滚见 `~/backup-butler-home-20260825.tgz`。勿删 `~/.config/butler-v5/` 与备份 tgz。

## §5 受保护文件 / 危险模式 / 工程约束

→ [`.cursorrules`](.cursorrules) 全文 + [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) §2-§4（v5 TypeScript+Effect-TS 约束，含 G1 lazy import / G2 契约 / G6 文件大小 / G7 env hygiene）

**R17 退役**（DESIGN §19 工程治理）：AI 守卫改由 commit review + 5 gate 兜底。

## §6 完整指南（cross-link 索引）

| 主题 | 读这里 |
|------|--------|
| 文档分层（L0-L5） | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §1 |
| 必读表注释 + 维护规则 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §3 + §6 |
| v5 TypeScript+Effect-TS 代码约束 | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md)（166 行，全文） |
| v4 保护层 / 钩子层 / 危险模式 | [`docs/architecture/v5-r10-handoff.md`](docs/architecture/v5-r10-handoff.md) §6 |
| 交接规约（工程治理，非产品运行时） | [`docs/plans/decisions/v5-engineering-handoff-2026-08.md`](docs/plans/decisions/v5-engineering-handoff-2026-08.md) |
| AI 守卫迁移清单 | [`docs/plans/archive/v5-ai-guard-migration-checklist-2026-08.md`](docs/plans/archive/v5-ai-guard-migration-checklist-2026-08.md) |
| D-series 累计 + 未来候选 | [`docs/plans/active/ROADMAP.md`](docs/plans/active/ROADMAP.md) |
| owner FAQ（D-series / audit-driven / 节奏） | [`docs/FAQ.md`](docs/FAQ.md) |
| 视觉架构图（Mermaid 4 张） | [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) |
| 生产加固指南（D77 T6） | [`docs/deployment/production-hardening.md`](docs/deployment/production-hardening.md) |
| **v5 功能清单（D80）**  | **[`docs/FEATURES.md`](docs/FEATURES.md)**                                        |
| **v5 API endpoint（D80）** | **[`docs/API_ENDPOINTS.md`](docs/API_ENDPOINTS.md)**                          |
| **v5 env vars（D80）**     | **[`docs/ENV.md`](docs/ENV.md)**                                                  |
| **v5 测试覆盖（D80）**   | **[`docs/TESTS.md`](docs/TESTS.md)**                                              |
| **v5 TODO / deferral（D80）** | **[`docs/TODO_DEFERRED.md`](docs/TODO_DEFERRED.md)**                                |
| **D-series audit findings（D80）** | **[`docs/AUDIT_FINDINGS.md`](docs/AUDIT_FINDINGS.md)**                              |
| 文档索引卡片（"我要…"） | [`docs/README.md`](docs/README.md) |
| 文档分层手册 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) |
| 黑板快照 | [`.blackboard/state.md`](.blackboard/state.md) |
| OSS 门面（CHANGELOG/CoC/SECURITY/Issue/PR） | [`CHANGELOG.md`](CHANGELOG.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · [`SECURITY.md`](SECURITY.md) · `.github/ISSUE_TEMPLATE/` · `.github/PULL_REQUEST_TEMPLATE.md` |

## §7 D78 索引（cycle 24 docs-batch）

本文件是 D78 T5 产物；其他 4 件套：

1. [`docs/plans/active/ROADMAP.md`](docs/plans/active/ROADMAP.md) — D22→D78 累计
2. [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) — 4 张 Mermaid
3. [`docs/FAQ.md`](docs/FAQ.md) — 10 段 owner FAQ
4. [`docs/README.md`](docs/README.md) §子目录速查 — 导航中心
