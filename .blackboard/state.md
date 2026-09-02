# WFXM BlackBoard State

_last_synced: 2026-09-02 (M1 已收口合 main 89d2c04f；Wave-3 并行分工已下发)
_handoff: .blackboard/shifts/2026-09-02-d49-exec-audit-handoff.md

**并行开发（2026-09-02 立项；2026-09-02 升级，见 `.blackboard/parallel/README.md`）**：monorepo 按包边界长期并行。各会话开 `par/<area>` topic 分支**自主推进、定期 rebase 自治适配**；**S1 仅在固定汇聚点（里程碑/发布快照）统一 rebase + 解共享冲突 + 全量 5-gate + 合 main**，日常不逐项合。会话：S1 / S2 domain / S3 ports+adapters（已退役主任务）/ S4 persistence / S5 runtime / S6 apps+cli。共享/承重文件（DESIGN/port-catalog/ports index/arch guard/state）仅 S1 可改。

> **2026-09-02 模型升级（业主确认）**：避免"每完成一项就汇聚 → 其他会话空等"。改为——①会话在自己 `par/*` 上推**一批自洽 commits** 再 push，各自跑**本包最小门禁**；②下游定期 `git rebase origin/main` 让上游改动自行流入并**自治适配**；③S1 只做**固定汇聚点**收口（全量 gate 从"每项一次"降到"每批一次"）。

## ✅ 首个汇聚点 M1（已收口 2026-09-02，合 main `89d2c04f`）

- **内容**：收口 `par/exec-audit` 在 main（D49）之上的 2 个未并提交：
  1. `bc704b6a` **exactOptionalPropertyTypes 基线清零**（apps/api 10 文件条件展开：wechat-project-surface / dev-quality-gate / schedule-worker / project-state / candidate-expires-sweeper / durable-memory-inject / project-knowledge-inject-sync-watch-worker）——清掉 main 遗留的 `wechat-project-surface.ts:314`（S1 决策登记中的"未清遗留"）。typecheck 全仓归零、lint 0 警、全量回归 1548（唯一 fail = bubblewrap 沙箱基线）。
  2. `dfa7c797` **并行模型升级黑板**（本文件 + parallel/README 的批次汇聚/自治 rebase 规约）。
- **收口结果（S1）**：FF 同步 main 到 D49 → `--no-ff` 合 `par/exec-audit` → 5-gate 全过（typecheck 全绿 / lint 0 警 / 全量 1548 仅 bubblewrap 基线）→ push `a721a90c..89d2c04f`。
- **收口后**：`par/exec-audit` 已消费，勿在其上续开；新会话基于新 main `89d2c04f` 开 `par/*`。

## 🌊 Wave-3 并行分工（S1 下发，2026-09-02）

| 会话 | 分支 | 工作 | 依赖 |
| --- | --- | --- | --- |
| S2 domain | `par/domain-ssot` | **SSOT `isTerminalRunStatus`**（transitions.ts 由 LEGAL_TRANSITIONS 无出边导出 + barrel；测试补正反例） | 无，S2+S1 协调 |
| S5 runtime | `par/runtime-ssot` | SSOT 消费侧（等 S2 合 main 后删本地 `TERMINAL_RUN_STATUSES`） | ⏳ S2 先合 |
| S4 persistence | `par/persistence-clean3` | 包内整理与完善（两实现 6 处差异核对 / db-open 测试基建 / 导出面核对） | 无 |
| S6 apps+cli | `par/exec-audit` 已消费→新开 | 包内整理与完善（subagent-worker/tools 行数评估 / exec-audit 边界测试 / Composition Root 口径） | 无 |

> 分支名仅建议；各会话也可按自身 `par/<area>` 规约起名。SSOT 是**唯一协调项**：S2 先做 domain 导出（标 `@S1`），S5 等 S2 合入后再 rebase 消费——**勿单会话抢先**。其余两会话完全独立。

**当前主线（D49 exec 审计记账）**：owner 重定向——Channel Port 退役（只用微信）；S6 开 exec 行为审计记账；S2/S4/S5 各包"整理与完善"。Wave-2 前半（D48）与 S6 exec（D49）均已并入 main。已并入：
- **D48 / Wave-2 前半（整理类）**：S2 domain `9639d265`（schedule/quiet-reply 边界，vitest 314）、S4 persistence `e7f8a8ed`（修基线 project-knowledge-store.ts:120 exactOptionalPropertyTypes + 边界测试，vitest 108）、S5 runtime `de3da1e2`（终态原子审计 transitionRunToTerminal/withTransaction；denyWaitingStep 走守卫；去 3 处冗余 as；runtime+arch 379）。
- **D49 / S6 exec 审计记账 `22d6691f`**：apps/api 新 `exec-audit.ts`（ExecAuditContext + recordExecAudit 统一落库）；覆盖 workspace-tools（run_command/read_file/write_file 含 bwrap 回退）、mcp-spawn→mcp-bootstrap（spawned）、wechat/dev-quality-gate。事件 `exec.executed`。纯观测、不签发权限、副作用咽喉未变；audit await 修复 PGlite 竞态。10 files +265/−43。

**5-gate（S1 合并后复核）**：D48 3 包 lint 0 警 / 全量 252 pass；D49 lint apps 0 警 / 全量 **253 files / 1545 pass / 1 skip**。多次全量回归仅剩两类环境 fail（cli 符号链伪影、workspace-tools.bubblewrap 缺系统沙箱，均在共享 worktree/沙箱缺依赖，真实生产树正常），无一在本批改动文件。**typecheck 基线遗留已在 M1 分支 bc704b6a 清零**（含原 `apps/api/wechat-project-surface.ts:314`）。

**S1 决策登记**：1. domain `./tools/types.js` 仅 `_archive/contracts` 消费 → **保留**（兼容层，非生产路径）。2. **SSOT isTerminalRunStatus 立项**（Wave-3 协调项，S2+S1 共同提交，勿单会话）。

**下一步**：**Wave-3 并行推进**（见上表）。SSOT（S2+S1）为协调主项，S5 等 S2 合入后消费；S4/S6 包内整理完全独立。下一汇聚点 **M2 待 S1 宣布**（各会话推进多轮后）。可选：MemoryService（§12）物化触发。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底
- 替未完成会话 commit 共享工作树 WIP（d89385ea 弃稿勿提交，已被 43f8a645/de3da1e2 接管）
- 造"第二实现"仅为可替换而硬物化 Memory/Channel Port

## 上一班

- 2026-09-02 (M1 收口)：S1 合 `par/exec-audit` 入 main（`89d2c04f`）——exactOptionalPropertyTypes 基线清零 + 并行模型升级黑板。5-gate 全过。Wave-3 分工下发（SSOT S2+S1 / S4 / S6）。
- 2026-09-02 (M1 宣布)：并行模型升级落盘 + 首个汇聚点宣布。见 .blackboard/parallel/README.md。
- 2026-09-02 (D49)：S6 exec 行为审计记账并入（FF 22d6691f）。lint apps 0 警，全量 253/1545。typecheck 基线遗留未清（wechat-project-surface.ts:314）。
- 2026-09-02 (D48 Wave-2 前半)：S1 把关合并 S2 domain + S4 persistence + S5 runtime（整理类）。3 包 lint 0 警，全量仅 3 环境 fail。typecheck 基线 2→1。SSOT isTerminalRunStatus 立项（S2+S1 协调）。
- 2026-09-02 (D47)：见 .blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md。
- 2026-09-02 (D46)：Repository Port 物化（in-memory RuntimeStore + ports RepositoryPort；推 D26B §20 #6 原 lock）。
- 2026-09-02 (D45)：owner-routes 按域拆分 7 子模块。
