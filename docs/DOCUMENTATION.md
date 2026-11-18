# Butler 文档体系与维护说明

> **更新**：2026-11-18 | **读者**：Owner、Cursor / Claude Code / Codex 等异构 Agent、贡献者
> **新会话**：[`../AGENTS.md`](../AGENTS.md) → [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) → [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) → 本文（按需）
> **工程交接**：规约 [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md)
>
> **与 [`README.md`](README.md) 的关系**：本文是**手册**（分层 / 维护规则 / 索引结构 / 变更记录）；[`README.md`](README.md) 是**卡片**（「我要…」问答快速链接表）。

---

## 1. 文档分层（读什么、何时读）

```text
L0  Agent 入口          AGENTS.md、.cursor/rules/
L1  目标架构            butler-v5/DESIGN.md
L2  当前实现事实        docs/architecture/wfxm-agent-runtime.html、
                        docs/architecture/v5-production-architecture-2026-08.md、
                        butler-v5/.env.example
L3  决策与路线          docs/plans/、docs/ROADMAP.md、docs/FAQ.md
L4  运维与配置          docs/deployment/、docs/ENV.md
```

| 层级 | 典型路径 | 用途 |
| --- | --- | --- |
| **L0 入口** | `AGENTS.md` | 新会话必读索引、v5 事实规则、撞点流程 |
| **L1 目标架构** | `butler-v5/DESIGN.md` | 务实模块化单体：Intake / Run Engine / Governance、混合数据、ScopedGrant、两条扩展接缝 |
| **L2 当前实现** | `docs/architecture/wfxm-agent-runtime.html` | 当前实现全景、分层测试 L1–L4 与第一阶段验收结论 |
| **L2 当前架构** | `docs/architecture/v5-production-architecture-2026-08.md` | 当前生产调用链、包与数据边界 |
| **L2 配置** | `butler-v5/.env.example` | v5 环境变量示例 |
| **L3 决策** | `docs/plans/decisions/v5-product-boundaries-2026-08.md` | 硬边界、条件准入、按需立项 |
| **L3 路线** | `docs/plans/active/v5-post-boundary-roadmap-2026-08.md` · `docs/ROADMAP.md` | P0–P4 顺序与 D-series 累计 |
| **L3 FAQ** | `docs/FAQ.md` | owner 视角的节奏、审计与取舍 |
| **L4 运维** | `docs/deployment/` | 自托管、生产加固与发版 |
| **L4 配置** | `docs/ENV.md` | v5 `BUTLER_V5_*` 环境变量 |

> 历史层（阶段评估、v4 历史与旧协同稿）已随 v4 退役删除，不再作为任何实现依据。

---

## 2. 目录索引（按文件夹）

### 2.1 `docs/architecture/`

| 文档 | 状态 |
| --- | --- |
| [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) | **v5 目标架构 SSOT（必读）** |
| [`v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) | **当前生产架构（必读）** |
| [`wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) | **当前实现全景与第一阶段验收（必读）** |
| [`v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) | 视觉架构图（Mermaid） |
| [`v5-r10-handoff.md`](architecture/v5-r10-handoff.md) | v5 迁移交接与保护层说明 |
| [`v5-r12-verification-2026-08.md`](architecture/v5-r12-verification-2026-08.md) | v5 R12 验证记录 |

### 2.2 `docs/deployment/`

- 自托管完整指南与生产加固（[`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) · [`deployment/production-hardening.md`](deployment/production-hardening.md)）

### 2.3 `docs/plans/`（分子目录）

索引：[`plans/README.md`](plans/README.md)

| 子目录 | 说明 |
| --- | --- |
| `active/` | v5 活跃计划（剩余开发、post-boundary 路线、各期 handoff） |
| `decisions/` | v5 决策（产品边界、工程交接、边界与取舍） |

### 2.4 `docs/adr/`、`docs/templates/`

- **adr/**：架构决策记录（含 [`adr/2026-08-08-v4-to-v5-supersession.md`](adr/2026-08-08-v4-to-v5-supersession.md)）
- **templates/**：权限、技能、实验 harness、项目 archetype，复制到 `.butler` 或 `projects`（[`templates/README.md`](templates/README.md)）

### 2.5 根层配置与梳理文档

- [`ENV.md`](ENV.md)：v5 `BUTLER_V5_*` 环境变量总表；示例见 [`../butler-v5/.env.example`](../butler-v5/.env.example)

---

## 3. 维护规则（改代码 / 改文档时）

### 3.1 改 `butler-v5/` 代码

1. 架构或调用链变化 → 更新 [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md)；目标架构变化才改 [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
2. 新增环境变量 → [`../butler-v5/.env.example`](../butler-v5/.env.example) + [`ENV.md`](ENV.md)
3. 测试增减 → [`TESTS.md`](TESTS.md)
4. 新能力 / 新接入 → 先过 [`plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md)
5. 工程约束 / 受保护文件 → [`GOVERNANCE.md`](GOVERNANCE.md)

### 3.2 新能力需求（产品 / 对标）

1. 先读 [`v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) 裁决流
2. 命中否决 → 拒绝或改边界，**不写**对照报告 P 表
3. 已有子集 → 更新对应 `*-capabilities` 速查
4. 可选立项 → 写入路线 / backlog，附验收与 env；接入新能力先过 [`plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md)

### 3.3 对照报告文首（统一模板）

```markdown
> **文档类型**：对照分析报告（正文 P0/P2 表为历史提炼，**非待办**）
> **状态**：…已落地子集…（见合并路线图 §9/§10）
> **决策入口**：[`v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md)
```

### 3.4 禁止事项

- 用已删除的历史文档或训练记忆推断当前模块路径
- 从对照报告正文 P0/P2 表直接排期（未经产品边界决策流）
- 在多个文档重复维护同一否决列表（以 product boundaries + out-of-scope 为 SSOT）
- 将 `reference/`（gitignore）当作 Butler 运行时依赖
- 批量刷新文档顶部日期；真实历史以 git log 为准

### 3.5 改工程交接

1. **活动规约**：[`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md)。
2. **不要**：把交接文档迁进 v5 Run/Task；恢复第二套 backlog。
3. **受保护面**：`.claude/settings.json` 仍须人工改口径。
4. **历史**：旧交接与班次记录已随 v4 退役删除，真实历史以 git log 为准。

### 3.6 改 AI 保护机制（`scripts/ai_guard/`、`.cursorrules`）

1. 保护脚本变更 → 同步 `.cursorrules` 与本文件 §3.6
2. 受保护文件清单变更 → 同步 [`GOVERNANCE.md`](GOVERNANCE.md) §5 与 [`../AGENTS.md`](../AGENTS.md) §4
3. hook 变更后运行 `bash scripts/ai_guard/install-pre-commit-hook.sh` 重新安装，CI 会检查源文件与 `.git/hooks/` 是否一致

---

## 4. 快速链接

| 我要… | 文档 |
| --- | --- |
| 总索引 | [`README.md`](README.md) |
| 规划命名 | [`plans/README.md`](plans/README.md) |
| 产品边界 / 条件准入 | [`plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) |
| v5 功能清单 | [`FEATURES.md`](FEATURES.md) |
| v5 API surface | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| v5 env vars | [`ENV.md`](ENV.md) |
| v5 测试覆盖 | [`TESTS.md`](TESTS.md) |
| v5 TODO / deferral | [`TODO_DEFERRED.md`](TODO_DEFERRED.md) |
| D-series audit findings | [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) |
| Feedback lessons | [`FEEDBACK.md`](FEEDBACK.md) |
| 工程治理一页纸 | [`GOVERNANCE.md`](GOVERNANCE.md) |
| 目录与命令 | [`../STRUCTURE.md`](../STRUCTURE.md) |
| Agent 规则 | [`../AGENTS.md`](../AGENTS.md) |

---

## 5. 变更记录

| 日期 | 说明 |
| --- | --- |
| 2026-08-20 | v5 目标架构二次收敛：三模块五实体；Task / Procedure / 独立记忆表延后；模型 Port 与副作用 Capability 分离 |
| 2026-08-20 | 工程交接收成短 `state.md`；claims / backlog / log 冻结 |
| 2026-09-21 | 新增 `ROADMAP.md` / `v5-current-state-diagrams.md` / `FAQ.md`；`docs/README.md` 增加子目录速查 |
| 2026-09-22 | 新增自托管指南 `deployment/SELF-HOSTING.md`；`pnpm demo` zero-LLM CLI REPL |
| 2026-11-18 | v4 退役：删除 v4 实现与历史文档层；分层收敛为 L0–L4，索引只保留 v5 现存文档 |
