# Butler v5 — Engineering Governance 一页纸

> **生成日期**: 2026-09-22 | **更新**: 2026-11-18（v4 退役后收敛） | **状态**: post-D79（127 ship 累计；D80 梳理 +22 ship = 149） | **读者**: Contributor / next-cycle 启动者 / 异构 agent（Cursor / Claude Code / Codex）
> **关系**:
> - 功能 / API / env / tests / deferral / audit findings / feedback → [综合梳理 docs](FEATURES.md) 等 7 件套
> - 目标架构（§1–§20 invariants）→ [`../DESIGN.md`](../DESIGN.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)
> - 文档分层手册 → [`DOCUMENTATION.md`](DOCUMENTATION.md)
> - Cursor / Trae 行为规则 → [`../.cursorrules`](../.cursorrules)
> - v5 TypeScript + Effect-TS 约束 → [`../AGENTS.md`](../AGENTS.md)
> - 状态快照 → [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md)
> - owner FAQ（D-series / audit-driven / 节奏判据）→ [`FAQ.md`](FAQ.md)

> **范围**: 本表覆盖 **工程治理** — 改东西之前必读 + 4 gate + 受保护面 + 撞点流程 + commit / ship 规范 + 文档分层 + 不要做。**不**覆盖产品运行时架构（详见 DESIGN §1–§20）。

---

## §0 总览

| 维度 | Source | 行数 / 关键点 |
|------|--------|----------------|
| Agent 必读 | `AGENTS.md` §1 (root) | 9 条表 |
| v5 事实规则 | `AGENTS.md` §2 | 6 条硬约束 |
| 撞点流程 | `AGENTS.md` §3 | 5 步 |
| 工程守卫 | `AGENTS.md` §4 | 受保护文件 + `[MANUAL-OVERRIDE]` |
| 受保护 / 危险 | `AGENTS.md` §5 | `.cursorrules` + `AGENTS.md` §2–§4 |
| Cursor 行为规则 | `.cursorrules` | v5 主线 + 行为规则 |
| v5 TS 约束 | `AGENTS.md` §2–§4 | 七级决策阶梯 + 工程约束 |
| 文档分层 (L0–L4) | `DOCUMENTATION.md` §1 | L0=入口 / L1=架构 / L2=实现 / L3=决策 / L4=运维 |
| 4 gate | `AGENTS.md` §2 + `.cursorrules` | typecheck + lint + test + build |
| Methodology 19·19 | `tests/acceptance/methodology.test.ts` | D53a N=3 prompt-freeze |

## §1 入口 + 必读（每 session 第 1 步）

> AGENTS.md §1 必读表（9 条）— 顺序：

1. [`DESIGN.md`](../DESIGN.md) — 改目标架构、概念、数据、安全、扩展边界
2. [`docs/architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) — 查当前生产 Loop / Gateway / 工具 / 数据 / 调用链
3. [`docs/architecture/wfxm-agent-runtime.html`](architecture/wfxm-agent-runtime.html) — 当前实现全景、分层测试 L1–L4 与第一阶段验收
4. [`docs/architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) — 视觉架构图（Mermaid 4 张）
5. [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) — 提需求 / 否决 / 条件准入 / 立项
6. [`docs/ROADMAP.md`](ROADMAP.md) — D-series 累计（127 ship）+ 后续候选
7. [`docs/FAQ.md`](FAQ.md) — owner 视角 FAQ（D-series / audit-driven / 节奏判据）
8. [`AGENTS.md`](../AGENTS.md) — v5 代码约束 + 包边界 + 测试
9. [`docs/DOCUMENTATION.md`](DOCUMENTATION.md) — 文档分层与维护规则

**新会话开篇前 30 秒**：读 [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md) → 本文件 → 撞点按 §3 流程。

## §2 v5 事实规则（6 条硬约束）

> AGENTS.md §2 — 改  前必读：

1. **生产路径**: `cli + apps/api → packages/runtime → adapters/persistence`
2. **目标 vs 实现**: `DESIGN.md`（目标架构）/ `v5-production-architecture`（当前事实）必须分开描述
3. **生产 DB schema**: 只认 [`packages/persistence/src/migrations/0001_initial.sql`](../packages/persistence/src/migrations/0001_initial.sql)
4. **新入口归一化**: Run Trigger →（Policy Ask 时 `waiting_approval`）→（需要时 ScopedGrant）→ Provider Boundary → Audit；模型调用不走副作用咽喉
5. **§20 KNOWN_ENTRY_POINTS**（D77 T5 强化）: 分 LLM + Non-LLM 2-tier；`/health` 等 non-LLM entry 不走模型路径
6. **MCP / 浏览器 / UI / 多 Channel / 调度 = 条件准入**（per DESIGN §7.1），非默认能力，非整类否决

## §3 撞点流程（5 步）

> AGENTS.md §3 + WFXM handoff discipline：

```text
1. owner 撞点 → 查 `ROADMAP.md` 最近 cycle 记录与最近一次 handoff 文档
2. 看 raw findings → .audit/Dxx/raw-findings.json
3. ship 模板：ship Dxx Tn <findings-id> <files>（per D77 7-ship 模式）
4. pause 模板：pause Dxx（在提交信息与 ROADMAP 记录暂停点）
5. audit 模板：audit Dxx（cycle 24+）
```

**重要**（per `feedback-handoff-discipline`）：owner 撞点 ≠ 默认 user-action；接活前穷尽 3 路径检查（CLI / MCP / env var）。

## §4 4 gate + L4 验收（改  后必跑）

> **4 gate**（`.cursorrules`）：typecheck + lint + test + build

```bash

pnpm typecheck   # 7 包类型检查
pnpm lint        # 代码规范检查
pnpm test        # 单元 / 契约 / 架构测试
pnpm build       # production build
```

补充验收：

```bash
bash scripts/typecheck-gate.sh              # v5 类型门禁（CI 同款）
npx tsx scripts/l4-smoke.ts                 # L4 主流程（需网关已启动）
npx tsx scripts/l4-smoke.ts --suite reliability
```

**Methodology 19·19**（D53a N=3 prompt-freeze）：

- `tests/acceptance/methodology.test.ts` — 19 cases ENGINEERING + 19 cases PRODUCT
- M15（D77 T7）— docker deploy artifacts 齐 + cross-link 一致
- 改 `AGENTS.md` 前必 grep methodology test cross-link assertion（per D78 T5.1 lesson）

## §5 受保护 / 承重文件（R17 后 review-only）

> **R17 (2026-08-28) 退役 v5 AI guard hook**（DESIGN §19 工程治理 ≠ 目标架构）。现“承重文件”概念由 commit review + 4 gate + architecture tests 兜底，**不强制 block AI 改**。

### §5.1 v5 生产承重文件

| 文件 | 风险 |
|------|------|
| `apps/api/src/wechat-inbound-butler.ts` | 微信入站 Loop |
| `apps/api/src/workspace-tools.ts` | 工作区工具 |
| `apps/api/src/tool-boundary.ts` | 工具边界 |
| `apps/api/src/capability-guard.ts` | 能力守卫 |
| `packages/runtime/src/agent-kernel.ts` | Agent 内核 |
| `packages/runtime/src/run-engine.ts` | Run 引擎 |
| `packages/persistence/src/event-bridge.ts` | 桥接层（driven adapter） |
| `packages/runtime/src/capability-boundary.ts` | 能力边界 |
| `packages/persistence/src/migrations/0001_initial.sql` | 生产 schema |

### §5.2 仓库级

| 文件 | 风险 |
|------|------|
| `.claude/settings.json` | AI 工具配置 |
| `scripts/ai_guard/protected_files.sh` | 受保护文件清单本身 |
| `.cursorrules` | Agent 行为规则 |

**修改前必跑**：

```bash
pnpm test && pnpm typecheck && pnpm lint
```

受保护文件被暂存时，commit message 必须含 `[MANUAL-OVERRIDE]`（由 `scripts/ai_guard/commit_msg_hook.sh` 强制）。

### §5.3 R17 后仍保留的 CI / git 机制

- `scripts/ai_guard/pre_commit_hook.sh` + `.git/hooks/pre-commit` — secret 扫描、迁移改动提示
- `scripts/ai_guard/commit_msg_hook.sh` + `.git/hooks/commit-msg` — `[MANUAL-OVERRIDE]` 强制
- `scripts/ai_guard/install-pre-commit-hook.sh` — 由 `butler-v5` 的 postinstall 调用，幂等同步 hooks
- `scripts/ai_guard/file_size_check.py` — `.py` 行数守卫（>800 警告 / >1200 阻止），随 pre-commit 调用
- architecture tests（`tests/architecture/`）：`dependency-direction.test.ts` / `package-membership.test.ts` / `mcp-contract.test.ts` / `side-effect-throat.test.ts` / `apps-layer-boundaries.test.ts` / `domain-zero-io.test.ts` 等 47 个

## §6 文档分层（L0–L4）

> `DOCUMENTATION.md` §1 必读 + 维护规则

```text
L0  Agent 入口          AGENTS.md、.cursor/rules/
L1  目标架构            DESIGN.md
L2  当前实现事实        wfxm-agent-runtime.html、v5-production-architecture、代码与 env example
L3  产品决策与路线      v5-product-boundaries、ADR、ROADMAP、FAQ
L4  运维与配置          deployment/、ENV.md
```

历史文档层已随 v4 退役删除；不要再引用或推断。

## §7 Commit / Ship 规范

### §7.1 Commit message（`feedback-bash-backtick-in-commit-message`）

```bash
# ✅ 正例
git commit -m 'fix: foo (commit abc1234)'      # single quote + 无内层反引号
git commit -m "fix: foo (commit abc1234)"        # 不带 backtick，直接括号

# ❌ 反模式
git commit -m "...commit \`abc1234\` ..."        # bash 把反引号当 $() 执行，SHA 被吃
```

**验证**：commit 后立刻 `git log -1 --format='%B'` 看 body 是否完整；有占位说明 body 被吃了。

### §7.2 Ship 模板（D-series）

```text
git commit -m 'docs(维度) Dxx Tn: <findings-id> <files>'
```

例：
- `docs(梳理) D80 T1: FEATURES.md 功能清单 (7 类别 / 60+ 功能 / 109 row)`
- `fix(audit) D73 T4 close 4 audit emit actor threading findings [MANUAL-OVERRIDE]`

### §7.3 [MANUAL-OVERRIDE] 标记

- 修改 §5 受保护文件 → commit message 必须含 `[MANUAL-OVERRIDE]`
- hook 检测到 `[MANUAL-OVERRIDE]` → 放行
- **不要**无受保护变更时加 → masking 审计

### §7.4 Push 路径（`feedback-wfxm-push-to-main`）

- 默认 `git push origin main`（D-series + post-D43）
- 只有用户显式说 "feature branch" / "PR" 才改路径

## §8 工程约束（`AGENTS.md` §5）

| 约束 | 阈值 | 行为 |
|------|------|------|
| 单文件行数 | >800 | 警告（建议拆分） |
| 单文件行数 | >1200 | 阻止（必须拆分） |
| 跨层 import | Core（runtime/domain）→ 具体适配器（persistence/adapters 实现） | 阻止 |
| 危险模式 | `import *` | 阻止 |
| 全局副作用 | 模块级 `new Map()` | 警告 |
| 死代码 | 未使用的导出 | 警告（`ts-prune` CI 检查） |

## §9 不要做（per `feedback-handoff-discipline`）

- 改 `wechat-inbound-butler.ts` 而无 `[MANUAL-OVERRIDE]`
- live smoke 升格 PR 硬门槛
- 替未完成会话 commit 共享工作树 WIP
- 造“第二实现”仅为可替换而硬物化 Memory/Channel Port
- 用已删除的历史文档内容作 Agent 实现依据
- 不经 4 步反查协议修改 system prompt / fixture / policy（per `feedback-temperature-model-changes-unprovable-2026-09-07`）
- 改 reply string 不带 test updates in same batch（per `feedback-d-batch-reply-string-test-update-batch`）— 30+ acceptance tests 跨 5+ 文件失败
- plan task 写 `@butler/persistence/...` 在 domain 层（per `feedback-plan-import-vs-arch-boundary`）— 改 local minimal interface + persistence 结构子型
- 文档顶部日期批量刷（per `feedback-doc-date-staleness`）— git log --follow 已反映真实历史
- `git commit -m "..."` 含反引号（per `feedback-bash-backtick-in-commit-message`）— bash 当 $() 替换；用 single quote
- 不带 raw findings JSON 就 ship audit-driven batch（per `feedback-audit-raw-findings-must-archive`）— D57 lesson #1

## §10 七级决策阶梯（`AGENTS.md` §2）

> 生成代码前依次检查，在第一个满足的阶梯停下：

```text
1. YAGNI         — 这个需求真的需要实现吗？
2. 代码库复用     — 是否已有类似实现？（先 grep 搜索）
3. 标准库        — TypeScript/Node.js 标准库是否已提供？
4. 原生平台      — Effect-TS 是否已内置此能力？
5. 已安装依赖    — 已安装的依赖是否能解决？
6. 一行代码      — 能否用一行代码解决？
7. 最小实现      — 最后才写最小可用代码
```

**防过度工程**：不做调用链深度限制、不做类型/函数预算硬性限制。用 `ts-prune`（CI 死代码检测）+ 文件大小门禁（>800 警告，>1200 阻止）替代。

## §11 状态快照 + 上一班

> 交接规约与状态口径以 [`plans/decisions/v5-engineering-handoff-2026-08.md`](plans/decisions/v5-engineering-handoff-2026-08.md) 为准；旧班次记录已随 v4 退役删除，真实历史见 git log。

**不要**：把交接文档迁进 v5 Run/Task；恢复第二套 backlog。

## §12 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能 / API / env / tests / deferral / audit / feedback | [综合梳理 docs](FEATURES.md) 等 7 件套 |
| 目标架构（§1–§20 invariants） | [`DESIGN.md`](../DESIGN.md) |
| Agent 入口（必读表） | [`AGENTS.md`](../AGENTS.md) |
| v5 TS 约束 + 包边界 | [`AGENTS.md`](../AGENTS.md) |
| Cursor 行为规则 | [`.cursorrules`](../.cursorrules) |
| 文档分层手册 | [`DOCUMENTATION.md`](DOCUMENTATION.md) |
| D-series 累计 | [`ROADMAP.md`](ROADMAP.md) |
| Owner FAQ | [`FAQ.md`](FAQ.md) |
| Methodology test | [`tests/acceptance/methodology.test.ts`](../tests/acceptance/methodology.test.ts) |

---

**End of GOVERNANCE.md** | D80 cycle + 2026-11-18 v4 退役收敛 | **8 件套（入口 + 撞点 + 4 gate + 受保护 + 文档分层 + commit + 约束 + 不要做）** | 改  之前必读
