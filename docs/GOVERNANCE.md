# Butler v5 — Engineering Governance 一页纸

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計; D80 梳理 +22 ship = 149) | **读者**: Contributor / next-cycle 启动者 / 异构 agent (Cursor / Claude Code / Codex)
> **关系**:
> - 功能 / API / env / tests / deferral / audit findings / feedback → [综合梳理 docs](FEATURES.md) 等 7 件套
> - 目标架构（§1-§20 invariants）→ [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)
> - 文档分层手册 → [`DOCUMENTATION.md`](DOCUMENTATION.md)
> - Cursor / Trae 行为规则 → [`../.cursorrules`](../.cursorrules)
> - v5 TypeScript+Effect-TS 约束 → [`../butler-v5/AGENTS.md`](../butler-v5/AGENTS.md)
> - 状态快照 → [`.blackboard/state.md`](../.blackboard/state.md)
> - owner FAQ（D-series / audit-driven / 节奏判据）→ [`FAQ.md`](FAQ.md)

> **范围**: 本表覆盖 **工程治理** — 改东西之前必读 + 5 gate + 受保护面 + 撞点流程 + commit / ship 规范 + 文档分层 + 不要做。**不**覆盖产品运行时架构（详见 DESIGN §1-§20）。

---

## §0 总览

| 维度 | Source | 行数 / 关键点 |
|------|--------|----------------|
| Agent 必读 | `AGENTS.md` §1 (root) | 8 条表 |
| v5 事实规则 | `AGENTS.md` §2 | 7 条硬约束 |
| 撞点流程 | `AGENTS.md` §3 | 5 步 |
| v4 legacy 兼容 | `AGENTS.md` §4 | 保留 + 不强约束 |
| 受保护 / 危险 | `AGENTS.md` §5 | `.cursorrules` + `butler-v5/AGENTS.md` §2-§4 |
| Cursor 行为规则 | `.cursorrules` | v5 主线 + 行为规则 |
| v5 TS 约束 | `butler-v5/AGENTS.md` §2-§4 | 七级决策阶梯 + 工程约束 |
| 文档分层 (L0-L5) | `DOCUMENTATION.md` §1 | L0=入口 / L1=架构 / L2=实现 / L3=决策 / L4=v4 / L5=历史 |
| 5 gate | `AGENTS.md` §2 + `.cursorrules` | typecheck + lint + test + test:archived + build |
| Methodology 19·19 | `butler-v5/tests/acceptance/methodology.test.ts` | D53a N=3 prompt-freeze |

## §1 入口 + 必读（每 session 第 1 步）

> AGENTS.md §1 必读表（8 条）— 顺序：

1. [`butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) — 改目标架构、概念、数据、安全、扩展边界
2. [`docs/architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) — 查当前生产 Loop / Gateway / 工具 / 数据 / 调用链
3. [`docs/architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) — 视觉架构图（Mermaid 4 张）
4. [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](plans/decisions/v5-product-boundaries-2026-08.md) — 提需求 / 否决 / 条件准入 / 立项
5. [`docs/ROADMAP.md`](ROADMAP.md) — D-series 累計（127 ship）+ 维度 2/3/4 候选
6. [`docs/FAQ.md`](FAQ.md) — owner 视角 FAQ（D-series / audit-driven / 节奏判据）
7. [`butler-v5/AGENTS.md`](../butler-v5/AGENTS.md) — v5 代码约束 + 包边界 + 测试
8. [`docs/DOCUMENTATION.md`](DOCUMENTATION.md) — 文档分层与维护规则

**新会话开篇前 30 秒**：读 `.blackboard/state.md` → 本文件 → 撞点按 §3 流程。

## §2 v5 事实规则（7 条硬约束）

> AGENTS.md §2 — 改 butler-v5/ 前必读：

1. **生产路径**: `butler-v5/cli + apps/api → packages/runtime → adapters/persistence`
2. **目标 vs 实现**: `butler-v5/DESIGN.md`（目标架构）/ `v5-production-architecture`（当前事实）必须分开描述
3. **`_archive/packages/{application,infrastructure}`** 未接入生产；不得用其单测声称能力已交付
4. **生产 DB schema**: 只认 [`packages/persistence/src/migrations/0001_initial.sql`](../butler-v5/packages/persistence/src/migrations/0001_initial.sql)
5. **新入口归一化**: Run Trigger →（Policy Ask 时 `waiting_approval`）→（需要时 ScopedGrant）→ Provider Boundary → Audit；模型调用不走副作用咽喉
6. **§20 KNOWN_ENTRY_POINTS**（D77 T5 强化）: 分 LLM + Non-LLM 2-tier；`/health` 等 non-LLM entry 不走模型路径
7. **MCP / 浏览器 / UI / 多 Channel / 调度 = 条件准入**（per DESIGN §7.1），非默认能力，非整类否决

## §3 撞点流程（5 步）

> AGENTS.md §3 + WFXM handoff discipline：

```
1. owner 撞点 → 查 MEMORY.md "Recent Sessions" 找最近 cycle memo
2. 看 raw findings → .audit/Dxx/raw-findings.json
3. ship 模板：ship Dxx Tn <findings-id> <files>（per D77 7-ship 模式）
4. pause 模板：pause Dxx（落 MEMORY.md + project-pause-state-*.md）
5. audit 模板：audit Dxx（cycle 24+）
```

**重要**（per `feedback-handoff-discipline`）：owner 撞点 ≠ 默认 user-action；接活前穷尽 3 路径检查（CLI / MCP / env var）。

## §4 5 gate + Methodology（改 butler-v5/ 后必跑）

> **5 gate**（`.cursorrules` line 103）：typecheck + lint + test + test:archived + build

```bash
cd butler-v5
pnpm typecheck   # 8 包类型检查
pnpm lint        # 代码规范检查
pnpm test        # 默认不含 _archive 测试
pnpm test:archived  # archived 脚手架测试
pnpm build       # production build
```

**Methodology 19·19**（D53a N=3 prompt-freeze）：
- `butler-v5/tests/acceptance/methodology.test.ts` — 19 cases ENGINEERING + 19 cases PRODUCT
- M15 (D77 T7) — docker deploy artifacts 齐 + cross-link 一致
- 改 `AGENTS.md` 前必 grep methodology test cross-link assertion（per D78 T5.1 lesson）

## §5 受保护 / 承重文件（R17 后 review-only）

> **R17 (2026-08-28) 退役 v5 AI guard hook**（DESIGN §19 工程治理 ≠ 目标架构）。现"承重文件"概念由 commit review + 5 gate + architecture tests 兜底，**不强制 block AI 改**。

### §5.1 v5 生产承重文件（v5 主线）

| 文件 | 风险 |
|------|------|
| `butler-v5/apps/api/src/wechat-inbound-butler.ts` | 微信入站 Loop |
| `butler-v5/apps/api/src/workspace-tools.ts` | 工作区工具 |
| `butler-v5/apps/api/src/tool-boundary.ts` | 工具边界 |
| `butler-v5/apps/api/src/capability-guard.ts` | 能力守卫 |
| `butler-v5/packages/runtime/src/agent-kernel.ts` | Agent 内核 |
| `butler-v5/packages/runtime/src/run-engine.ts` | Run 引擎 |
| `butler-v5/packages/persistence/src/event-bridge.ts` | 桥接层（driven adapter） |
| `butler-v5/packages/runtime/src/capability-boundary.ts` | 能力边界 |
| `butler-v5/packages/persistence/src/migrations/0001_initial.sql` | 生产 schema |

### §5.2 仓库级 + Legacy v4

| 文件 | 风险 |
|------|------|
| `pyproject.toml` | 项目配置 |
| `.claude/settings.json` | AI 工具配置 |
| `.blackboard/README.md` | 交接规约 |
| `butler/core/agent_loop/loop.py` | v4 核心循环（legacy） |
| `butler/contracts/__init__.py` | v4 契约层入口（legacy） |

**修改前必跑**：
- v5 文件：改后 `cd butler-v5 && pnpm test && pnpm typecheck && pnpm lint`
- v4 文件：`./scripts/butler-pytest-fast-gate.sh`

### §5.3 R17 后仍保留的 CI/git 机制

- `scripts/ai_guard/file_size_check.py` — CI gate + local gate
- `scripts/ai_guard/pre_commit_hook.sh` + `.git/hooks/pre-commit` — git pre-commit（修 protected 时需 `[MANUAL-OVERRIDE]`）
- 12 个 architecture tests：`tests/architecture/dependency-direction.test.ts` / `package-membership.test.ts` / `mcp-contract.test.ts` / `side-effect-throat.test.ts` / `apps-layer-boundaries.test.ts` / `domain-zero-io.test.ts` / `r2-end-to-end.test.ts` 等

## §6 文档分层（L0-L5）

> `DOCUMENTATION.md` §1 必读 + 维护规则

```
L0  Agent 入口         AGENTS.md、.cursor/rules/
L1  目标架构           butler-v5/DESIGN.md
L2  当前实现事实       v5-production-architecture、v5-r10-handoff、代码与 env example
L3  产品决策与路线     v5-product-boundaries、ADR、v5-post-boundary-roadmap
L4  v4 / 对照历史      v4 architecture、comparison、learning-plan
L5  历史（勿作依据）   docs/history/、已 superseded 文档
```

**L5 警告**：`docs/history/` 不作 Agent 实现依据。

## §7 Commit / Ship 规范

### §7.1 Commit message（`feedback-bash-backtick-in-commit-message`）

```bash
# ✅ 正例
git commit -m 'fix: foo (commit abc1234)'      # single quote + 无内层反引号
git commit -m "fix: foo (commit abc1234)"        # 不带 backtick，直接括号

# ❌ 反模式
git commit -m "...commit \`abc1234\` ..."        # bash 把反引号当 $() 执行，SHA 被吃
```

**验证**：commit 后立刻 `git log -1 --format='%B'` 看 body 是否完整；有 `/ / ` 占位说明 body 被吃了。

### §7.2 Ship 模板（D-series）

```
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

## §8 工程约束（`butler-v5/AGENTS.md` §5）

| 约束 | 阈值 | 行为 |
|------|------|------|
| 单文件行数 | >800 | 警告（建议拆分） |
| 单文件行数 | >1200 | 阻止（必须拆分） |
| 跨层 import | Core（runtime/domain）→ 具体适配器（persistence/adapters 实现） | 阻止 |
| 危险模式 | `import *` | 阻止 |
| 全局副作用 | 模块级 `new Map()` | 警告 |
| 死代码 | 未使用的导出 | 警告（`ts-prune` CI 检查） |

## §9 不要做（per `feedback-handoff-discipline` + 黑板 state.md）

- 改 `wechat-inbound-butler.ts` 而无 `[MANUAL-OVERRIDE]`
- live smoke 升格 PR 硬门槛
- 替未完成会话 commit 共享工作树 WIP
- 造"第二实现"仅为可替换而硬物化 Memory/Channel Port
- 用 `_archive/packages/{application,infrastructure}` 单测声称能力已交付
- 用 `docs/history/` 内容作 Agent 实现依据
- 不经 4 步反查协议修改 system prompt / fixture / policy（per `feedback-temperature-model-changes-unprovable-2026-09-07`）
- 改 reply string 不带 test updates in same batch（per `feedback-d-batch-reply-string-test-update-batch`）— 30+ acceptance tests 跨 5+ 文件失败
- plan task 写 `@butler/persistence/...` 在 domain 层（per `feedback-plan-import-vs-arch-boundary`）— 改 local minimal interface + persistence 结构子型
- 文档顶部日期批量刷（per `feedback-doc-date-staleness`）— git log --follow 已反映真实历史
- `git commit -m "..."` 含反引号（per `feedback-bash-backtick-in-commit-message`）— bash 当 $() 替换；用 single quote
- 不带 raw findings JSON 就 ship audit-driven batch（per `feedback-audit-raw-findings-must-archive`）— D57 lesson #1

## §10 七级决策阶梯（`butler-v5/AGENTS.md` §2）

> 生成代码前依次检查，在第一个满足的阶梯停下：

```
1. YAGNI         — 这个需求真的需要实现吗？
2. 代码库复用     — 是否已有类似实现？（先 grep 搜索）
3. 标准库        — TypeScript/Node.js 标准库是否已提供？
4. 原生平台      — Effect-TS 是否已内置此能力？
5. 已安装依赖    — 已安装的依赖是否能解决？
6. 一行代码      — 能否用一行代码解决？
7. 最小实现      — 最后才写最小可用代码
```

**防过度工程**：不做调用链深度限制、不做类型/函数预算硬性限制。用 `ts-prune`（CI 死代码检测）+ 文件大小门禁（>800 警告，>1200 阻止）替代。

## §11 §11 状态快照 + 上一班（per `.blackboard/state.md`）

```
_last_synced: 2026-09-04 (P1+P2 全闭环)
HEAD: 744012db  (D79 T4 doc cross-links)
State: PAUSED post-D79-FULL-CYCLE — 维度 2 (demo + E2E + self-hosting) 完成
```

**完整活动规约**：`plans/decisions/v5-engineering-handoff-2026-08.md`
**默认只更新短 `state.md`**
**不要**：把黑板迁进 v5 Run/Task；恢复 claims / 第二套 backlog；为 `butler/blackboard` 扩 schema 当新功能

## §12 §12 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能 / API / env / tests / deferral / audit / feedback | [综合梳理 docs](FEATURES.md) 等 7 件套 |
| 目标架构（§1-§20 invariants） | [`butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) |
| Agent 入口（必读表） | [`AGENTS.md`](../AGENTS.md) |
| v5 TS 约束 + 包边界 | [`butler-v5/AGENTS.md`](../butler-v5/AGENTS.md) |
| Cursor 行为规则 | [`.cursorrules`](../.cursorrules) |
| 文档分层手册 | [`DOCUMENTATION.md`](DOCUMENTATION.md) |
| 状态快照 | [`.blackboard/state.md`](../.blackboard/state.md) |
| D-series 累計 | [`ROADMAP.md`](ROADMAP.md) |
| Owner FAQ | [`FAQ.md`](FAQ.md) |
| Methodology test | [`butler-v5/tests/acceptance/methodology.test.ts`](../butler-v5/tests/acceptance/methodology.test.ts) |

---

**End of GOVERNANCE.md** | D80 cycle 26 inventory batch | **8 件套（入口 + 撞点 + 5 gate + 受保护 + 文档分层 + commit + 约束 + 不要做）** | 改 butler-v5/ 之前必读