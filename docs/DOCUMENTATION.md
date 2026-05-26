# Butler 文档体系与维护说明

> **更新**：2026-05-26 | **读者**：主公、Cursor Agent、贡献者  
> **新会话**：[`../AGENTS.md`](../AGENTS.md) → [`architecture/v4-architecture.md`](architecture/v4-architecture.md) → 本文（按需）

---

## 1. 文档分层（读什么、何时读）

```text
L0  Agent 入口          AGENTS.md、.cursor/rules/
L1  实现事实来源        v4-architecture.md、config/reference.md、.env.example
L2  决策与边界          roadmap-backlog-and-boundaries（否决 / Backlog）
L3  已落地速查          *-capabilities-2026-05.md、各路线图 §9/§10
L4  对照全文（归档读）  *-comparison-report / *-learning-plan 正文
L5  历史（勿作实现依据） docs/history/、design.md §11+
```

| 层级 | 典型路径 | 用途 |
|------|----------|------|
| **L1 架构** | `docs/architecture/` | 模块划分、Loop/Gateway、ADR |
| **L1 配置** | `docs/config/`、`/.env.example` | `BUTLER_*` 权威默认值 |
| **L2 决策** | `docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md` | 否决、深化边界、可选 Backlog |
| **L2 规划索引** | `docs/plans/README.md` | 命名对照（CC / 整理 / 外部对标） |
| **L3 运维指南** | `docs/guides/` | 微信发版、冒烟、Runtime、外部对标验收 |
| **L3 运维阈值** | `docs/ops/` | `/诊断` 指标说明 |
| **L4 对照报告** | `docs/plans/*-comparison*.md`、`docs/agent-analysis-2026-05/` | 竞品/本轮分析归档；**正文旧表非待办** |
| **L4 路线图** | `docs/plans/*-improvement-roadmap*.md` | PR 核对表（§9/§10）；历史 PR 叙述 |
| **L5 历史** | `docs/history/` | v0.5–v3，已删除实现 |
| **产品** | `docs/design/design.md` | 产品摘要；§9 对照表可用 |

---

## 2. 三类「规划」文档（勿混淆）

| 类型 | 特征 | 读完应做什么 |
|------|------|----------------|
| **路线图（improvement-roadmap）** | 有 PR-F / PR-X / PR1–PR6；§9/§10 为核对表 | 查 §9/§10 是否 ✅；**勿**从 §3–§5 旧 P 表立项 |
| **对照报告（comparison-report）** | 长文 + P0/P2 提炼表 | 查文首 **落地状态**；否决见 roadmap-backlog §1 |
| **学习计划（learning-plan）** | 单源对标、已收口多 | 仅作验收索引；defer 见 external-reference-deferred |

**统一决策入口**：[`plans/roadmap-backlog-and-boundaries-2026-05.md`](plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)

---

## 3. 已收口主线（2026-05-25）

下列主线 **无后续必做 PR**；新能力须对照 §2 决策流，不得从对照报告正文复活待办。

| 主线 | 路线图 / 速查 | 守门 |
|------|----------------|------|
| CC 线束 P0–P4 | `cc-butler-gap-analysis` | `test_cc_p3_p4_features` 等 |
| 四报告 PR1–PR6 | `four-reports-improvement-roadmap` §9 | `four-reports-capabilities` |
| 五报告 PR-F1–F6 | `five-reports-improvement-roadmap` §9 | `five-reports-capabilities` |
| 五报告 P5–P10 | `five-reports-not-done` §3 | `butler-five-reports-gate.sh` |
| 外部 Agent PR-X1–X6 | `external-agent-reports-improvement-roadmap` §10 | `test_external_agent_*` |
| 外部对标 A/B/C + defer | `guides/external-reference-roadmap` | `phase-abc-external-reference` |
| OpenCode / OpenClaw / OMO | 各 learning-plan | 各 `test_*` |
| 仓库整理 P0–P3 | `consolidation-*` | — |

**仍活跃的产品规划**：[`plans/post-consolidation-roadmap-2026-05.md`](plans/active/post-consolidation-roadmap-2026-05.md)（运营、语料、多项目 — 与对标正交）

---

## 4. 目录索引（按文件夹）

### 4.1 `docs/architecture/`

| 文档 | 状态 |
|------|------|
| [`v4-architecture.md`](architecture/v4-architecture.md) | **当前架构（必读）** |
| [`hermes-decoupling.md`](architecture/hermes-decoupling.md) | 已完成 |
| [`hermes-butler-comparison-2026-05.md`](architecture/hermes-butler-comparison-2026-05.md) | 对照全文 |
| [`memory-roadmap.md`](architecture/memory-roadmap.md) | 记忆能力路线图（P0–P2 已落地） |
| [`project-layer-wechat-plan.md`](architecture/project-layer-wechat-plan.md) | 项目层微信规划 |
| 其余 ADR / 设计稿 | 按需 |

### 4.2 `docs/guides/`

索引：[`guides/README.md`](guides/README.md)

| 类别 | 代表文档 |
|------|----------|
| **项目总览 / 依赖** | `capabilities-index-2026-05`、`dependency-policy-2026-05` |
| **生产运维** | `wechat-gateway-ops`、`wechat-daily-smoke-checklist` |
| **能力速查** | `four-reports-capabilities`、`five-reports-capabilities`、`external-agent-reports-capabilities` |
| **外部对标验收** | `external-reference-roadmap`、`phase-abc-external-reference`、`external-reference-deferred` |
| **Sprint / Codex** | `sprint-roadmap`、`sprint-codex-c0/c1/c2` |
| **接入** | `project-onboarding`、`memory-ops`、`runtime-ops` |

### 4.3 `docs/plans/`（分子目录）

索引：[`plans/README.md`](plans/README.md)

| 子目录 | 说明 |
|--------|------|
| `active/` | `post-consolidation`、`cc-butler-gap-analysis` |
| `decisions/` | **roadmap-backlog**、out-of-scope、five-reports-not-done |
| `roadmaps/` | 四/五/外部 Agent 已收口路线图 §9/§10 |
| `comparisons/` | 对照全文（**非待办**） |
| `corpus/` | 语料与微信场景 |
| `archive/` | 已完成实施、历史分析 |

发版：[`guides/release-runbook-2026-05.md`](guides/release-runbook-2026-05.md) · 能力索引：[`guides/capabilities-index-2026-05.md`](guides/capabilities-index-2026-05.md)

### 4.4 `docs/templates/`、`docs/reviews/`、`docs/history/`

- **templates/**：权限、技能、实验 harness、项目 archetype — 复制到 `.butler/` 或 `projects/`
- **reviews/**：阶段性评估（非实现规范）
- **history/**：**勿**作 Agent 实现依据
- **agent-analysis-2026-05/**：2026-05 Canvas/Plan 整理稿；属于分析归档，当前实现仍以 `v4-architecture` / `config/reference` / `roadmap-backlog` 为准

---

## 5. 语料与测试文档（专项）

与 Butler Loop 对标 **正交**；改 `tests/corpus/` 或 `message_handler` 时读。

| 文档 | 用途 |
|------|------|
| [`plans/corpus-testing-module-design-2026-05.md`](plans/corpus/corpus-testing-module-design-2026-05.md) | 语料模块设计 |
| [`plans/wechat-real-coverage-matrix-2026-05.md`](plans/corpus/wechat-real-coverage-matrix-2026-05.md) | 真机覆盖矩阵 |
| [`plans/wechat-dev-conversation-scenarios-2026-05.md`](plans/corpus/wechat-dev-conversation-scenarios-2026-05.md) | 开发对话场景 |
| [`plans/dev-assistant-corpus-history-2026-05.md`](plans/corpus/dev-assistant-corpus-history-2026-05.md) | 语料 v1–v4 版本史 |
| [`guides/project-intro-for-utterance-corpus.md`](guides/project-intro-for-utterance-corpus.md) | 语料项目介绍 |

命令：[`../CONTRIBUTING.md`](../CONTRIBUTING.md) 语料节、`./scripts/corpus-test.sh`

---

## 6. 维护规则（改代码 / 改文档时）

### 6.1 改 `butler/core` 或 `butler/gateway`

1. 更新 [`architecture/v4-architecture.md`](architecture/v4-architecture.md) 相关节  
2. 新 `BUTLER_*` → [`config/reference.md`](config/reference.md) + `.env.example`  
3. 改 `pyproject.toml` 依赖分层（`dependencies` / `optional-dependencies`）→ 同步 [`guides/dependency-policy-2026-05.md`](guides/dependency-policy-2026-05.md)  
4. 若属 CC 线束 → [`plans/cc-butler-gap-analysis-2026-05.md`](plans/active/cc-butler-gap-analysis-2026-05.md) §3  
5. 阈值 → [`ops/diagnostic-thresholds.md`](ops/diagnostic-thresholds.md)

### 6.2 新能力需求（产品 / 对标）

1. 先读 [`roadmap-backlog-and-boundaries-2026-05.md`](plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) §0 决策流  
2. 命中否决 → 拒绝或改边界，**不写**对照报告 P 表  
3. 已有子集 → 更新 §2 深化边界 + 对应 `*-capabilities` 速查  
4. 可选立项 → 写入 roadmap-backlog §3，附验收与 env

### 6.3 对照报告文首（统一模板）

新增或修订对照报告时，文首应含：

```markdown
> **文档类型**：对照分析报告（正文 P0/P2 表为历史提炼，**非待办**）
> **状态**：…已落地子集…（见合并路线图 §9/§10）
> **决策入口**：[`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md)
```

### 6.4 禁止事项

- 从 `docs/history/` 或 `design.md` §11+ 推断当前模块路径  
- 从对照报告正文 P0/P2 表直接排期（未经 roadmap-backlog 决策流）  
- 在多个文档重复维护同一否决列表（以 roadmap-backlog + out-of-scope 为 SSOT）  
- 将 `reference/`（gitignore）当作 Butler 运行时依赖

---

## 7. 快速链接

| 我要… | 文档 |
|--------|------|
| 总索引 | [`README.md`](README.md) |
| 规划命名 | [`plans/README.md`](plans/README.md) |
| 指南列表 | [`guides/README.md`](guides/README.md) |
| 否决 / Backlog | [`plans/roadmap-backlog-and-boundaries-2026-05.md`](plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) |
| 目录与命令 | [`../STRUCTURE.md`](../STRUCTURE.md) |
| Agent 规则 | [`../AGENTS.md`](../AGENTS.md) |

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：文档分层、三类规划、已收口主线、语料专项、维护规则 |
| 2026-05-25 | 全库整理：索引对齐、对照报告文首状态、语料/归档分表 |
| 2026-05-25 | 合并 phase-a/b/c → phase-abc；语料 v1–v4 → corpus-history；精简 plans/README、reference-learning-plan |
| 2026-05-25 | plans/ 分子目录；瘦身 AGENTS；release-runbook、capabilities-index、docs-lint.sh |
| 2026-05-26 | 新增项目状态总览与依赖策略索引；补充 pyproject 依赖分层同步规则 |
