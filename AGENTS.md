# Cursor / Agent 工作说明（WFXM / Butler v5）

> **Butler v5 是唯一活动产品主线；v4 实现与历史文档层已从仓库移除。** 新会话不要用训练记忆或任何已删除的历史文档推断 v5 实现。
> **新会话开篇前 30 秒**：读本文件 → [`docs/architecture/wfxm-agent-runtime.html`](docs/architecture/wfxm-agent-runtime.html) → 撞点按 §3 流程。

## §1 必读表（9 条）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | [`butler-v5/DESIGN.md`](butler-v5/DESIGN.md) | 改目标架构、概念、数据、安全或扩展边界 |
| 2 | [`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md) | 查当前生产 Loop / Gateway / 工具 / 数据 / 调用链 |
| 3 | [`docs/architecture/wfxm-agent-runtime.html`](docs/architecture/wfxm-agent-runtime.html) | 查当前实现全景、分层测试 L1–L4 与第一阶段验收结论 |
| 4 | [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) | 视觉架构图（Mermaid 4 张） |
| 5 | [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](docs/plans/decisions/v5-product-boundaries-2026-08.md) | 提需求 / 否决 / 条件准入 / 立项 |
| 6 | [`docs/ROADMAP.md`](docs/ROADMAP.md) | D-series 累计（117 ship）+ 维度 2/3/4 候选 |
| 7 | [`docs/FAQ.md`](docs/FAQ.md) | owner 视角 FAQ（D-series / audit-driven / 节奏判据） |
| 8 | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) | v5 代码约束 + 包边界 + 测试 |
| 9 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层与维护规则 |

## §2 v5 事实规则（6 条硬约束）

1. **生产路径**: `butler-v5/cli + apps/api → packages/runtime → adapters/persistence`
2. **目标 vs 实现**: `butler-v5/DESIGN.md`（目标架构）/ `v5-production-architecture`（当前事实）必须分开描述
3. **生产 DB schema**: 只认 [`packages/persistence/src/migrations/0001_initial.sql`](butler-v5/packages/persistence/src/migrations/0001_initial.sql)
4. **新入口归一化**: Run Trigger →（Policy Ask 时 `waiting_approval`）→（需要时 ScopedGrant）→ Provider Boundary → Audit；模型调用不走副作用咽喉
5. **§20 KNOWN_ENTRY_POINTS**（D77 T5 强化）: 分 LLM + Non-LLM 2-tier；`/health` 等 non-LLM entry 不走模型路径
6. **MCP / 浏览器 / UI / 多 Channel / 调度 = 条件准入**（per DESIGN §7.1），非默认能力，非整类否决

## §3 撞点流程（5 步）

1. **owner 撞点** → 先读本文件与 [`docs/architecture/wfxm-agent-runtime.html`](docs/architecture/wfxm-agent-runtime.html) 的当前实现与验收结论
2. **看 findings 来源**: 评估产物 `.eval-runs/`、CI 日志或用户反馈（`raw-findings` 目录已随历史审计一并移除）
3. **ship 模板**: `ship Dxx Tn <findings-id> <files>`（per D77 7-ship 模式）
4. **pause 模板**: `pause Dxx`（在提交信息与 ROADMAP 记录暂停点）
5. **audit 模板**: `audit Dxx`（cycle 24+）

## §4 工程守卫（review-only）

`.cursorrules` 与 `scripts/ai_guard/` 仍保留受保护文件与危险模式约束：

- 受保护文件清单以 [`scripts/ai_guard/protected_files.sh`](scripts/ai_guard/protected_files.sh) 为准；修改其中文件须在提交信息加 `[MANUAL-OVERRIDE]`
- 继续遵守保护，不得擅自移除
- 守卫规则是**工程治理**，不是 v5 产品架构或能力现状的事实来源
- 修改 AI 守卫 / `.claude/settings.json` / 受保护文件仍需人工操作

**D1 已执行（2026-08-25）**: 旧版 Butler 用户目录（`~/.butler`）已删除；回滚见 `~/backup-butler-home-20260825.tgz`。勿删 `~/.config/butler-v5/` 与备份 tgz。

## §5 受保护文件 / 危险模式 / 工程约束

→ [`.cursorrules`](.cursorrules) 全文 + [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) §2-§4（v5 TypeScript + pnpm monorepo 约束，含 G1 lazy import / G2 契约 / G6 文件大小 / G7 env hygiene）

**R17 退役**（DESIGN §19 工程治理）：AI 守卫改由 commit review + 4 gate 兜底。

## §6 完整指南（cross-link 索引）

| 主题 | 读这里 |
|------|--------|
| 文档分层（L0-L4） | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §1 |
| 维护规则 / 索引结构 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §2–§3 |
| v5 TypeScript + pnpm monorepo 代码约束 | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) |
| 工程守卫 / 受保护文件 / 危险模式 | [`scripts/ai_guard/protected_files.sh`](scripts/ai_guard/protected_files.sh) · [`.cursorrules`](.cursorrules) |
| 交接规约（工程治理，非产品运行时） | [`docs/plans/decisions/v5-engineering-handoff-2026-08.md`](docs/plans/decisions/v5-engineering-handoff-2026-08.md) |
| D-series 累计 + 未来候选 | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| owner FAQ（D-series / audit-driven / 节奏） | [`docs/FAQ.md`](docs/FAQ.md) |
| 视觉架构图（Mermaid 4 张） | [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) |
| 生产加固指南（D77 T6） | [`docs/deployment/production-hardening.md`](docs/deployment/production-hardening.md) |
| **v5 功能清单（D80）**  | **[`docs/FEATURES.md`](docs/FEATURES.md)**                                        |
| **v5 API endpoint（D80）** | **[`docs/API_ENDPOINTS.md`](docs/API_ENDPOINTS.md)**                          |
| **v5 env vars（D80）**     | **[`docs/ENV.md`](docs/ENV.md)**                                                  |
| **v5 测试覆盖（D80）**   | **[`docs/TESTS.md`](docs/TESTS.md)**                                              |
| **v5 TODO / deferral（D80）** | **[`docs/TODO_DEFERRED.md`](docs/TODO_DEFERRED.md)**                                |
| **D-series audit findings（D80）** | **[`docs/AUDIT_FINDINGS.md`](docs/AUDIT_FINDINGS.md)**                              |
| **Feedback lessons（D80）**     | **[`docs/FEEDBACK.md`](docs/FEEDBACK.md)**                                                  |
| **工程治理一页纸（D80）**       | **[`docs/GOVERNANCE.md`](docs/GOVERNANCE.md)**                                            |
| 文档索引卡片（"我要…"） | [`docs/README.md`](docs/README.md) |
| 文档分层手册 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) |
| OSS 门面（CHANGELOG/CoC/SECURITY/Issue/PR） | [`CHANGELOG.md`](CHANGELOG.md) · [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) · [`SECURITY.md`](SECURITY.md) · `.github/ISSUE_TEMPLATE/` · `.github/PULL_REQUEST_TEMPLATE.md` |

## §7 D78 索引（cycle 24 docs-batch）

本文件是 D78 T5 产物；其他 4 件套：

1. [`docs/ROADMAP.md`](docs/ROADMAP.md) — D22→D78 累计
2. [`docs/architecture/v5-current-state-diagrams.md`](docs/architecture/v5-current-state-diagrams.md) — 4 张 Mermaid
3. [`docs/FAQ.md`](docs/FAQ.md) — 10 段 owner FAQ
4. [`docs/README.md`](docs/README.md) §子目录速查 — 导航中心
