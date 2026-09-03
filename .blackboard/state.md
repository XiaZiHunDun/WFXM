# WFXM BlackBoard State

_last_synced: 2026-09-03 (M3 approval + eval timeout resilience merged)
_handoff: .blackboard/shifts/2026-09-02-d49-exec-audit-handoff.md

## M3 approval-runtime hardening (merged 2026-09-03)

- Verification: approveWaitingStep idempotent for expired/non-waiting (alreadyProcessed, no double grant); denyWaitingStep via transitionRunToTerminal guard; store stateless -> pending steps fully recoverable.
- Acceptance tests (+132, 3 files): domain types.test.ts +2 (expired/exhausted grant -> Ask deny); runtime approval-runtime.test.ts +2 (fresh store instance resume; restart-then-expired -> no grant, run terminal).
- Test env baseline: bubblewrap slirp integration env-gated (BUTLER_V5_TEST_FULL_SANDBOX=1), default skip; baseline green.
- 5-gate: typecheck green / lint 0 warn / deadcode PASS / file-size PASS / full 262/263 files, 1696/1700 (only eval/14 timeout under overload; 6.9s solo).
- Noted (untouched): domain/workflows/ unwired but maps to deferred roadmap (DAG/parallel); keep.

## 🎯 eval 场景超时韧性（已收口 2026-09-03）

- **根因**：多轮 eval 场景（05/14/15）每轮重建 PGlite+wiring（migrate ~700ms/轮），全量并行 CPU 争抢下超时；eval/14 是全量唯一不稳定 fail。
- **修复**：eval harness 新增 `makeEvalHarness`/`closeEvalHarness` + `RunScenarioInput.harness`，DB+wiring 建一次跨轮复用；`runEvalScenario` 仅在自有 DB 时 close。
- **效果**：eval/14 6.9s→~2.0s，setup 755ms/轮→0；eval/05 1.18s、eval/15 1.95s；所有 22 个 eval 场景 standalone PASS，typecheck+lint 绿。
- commit `e90609dd`（4 文件 +88/−20）。


**并行开发（2026-09-02 立项；2026-09-02 升级，见 `.blackboard/parallel/README.md`）**：monorepo 按包边界长期并行。各会话开 `par/<area>` topic 分支**自主推进、定期 rebase 自治适配**；**S1 仅在固定汇聚点（里程碑/发布快照）统一 rebase + 解共享冲突 + 全量 5-gate + 合 main**，日常不逐项合。会话：S1 / S2 domain / S3 ports+adapters（已退役主任务）/ S4 persistence / S5 runtime / S6 apps+cli。共享/承重文件（DESIGN/port-catalog/ports index/arch guard/state）仅 S1 可改。

> **2026-09-02 模型升级（业主确认）**：避免"每完成一项就汇聚 → 其他会话空等"。改为——①会话在自己 `par/*` 上推**一批自洽 commits** 再 push，各自跑**本包最小门禁**；②下游定期 `git rebase origin/main` 让上游改动自行流入并**自治适配**；③S1 只做**固定汇聚点**收口（全量 gate 从"每项一次"降到"每批一次"）。

## ✅ 首个汇聚点 M1（已收口 2026-09-02，合 main `89d2c04f`）　→　✅ M2（已收口 2026-09-03，合 main `4a6e628f`）

- **内容**：收口 `par/exec-audit` 在 main（D49）之上的 2 个未并提交：
  1. `bc704b6a` **exactOptionalPropertyTypes 基线清零**（apps/api 10 文件条件展开：wechat-project-surface / dev-quality-gate / schedule-worker / project-state / candidate-expires-sweeper / durable-memory-inject / project-knowledge-inject-sync-watch-worker）——清掉 main 遗留的 `wechat-project-surface.ts:314`（S1 决策登记中的"未清遗留"）。typecheck 全仓归零、lint 0 警、全量回归 1548（唯一 fail = bubblewrap 沙箱基线）。
  2. `dfa7c797` **并行模型升级黑板**（本文件 + parallel/README 的批次汇聚/自治 rebase 规约）。
- **收口结果（S1）**：FF 同步 main 到 D49 → `--no-ff` 合 `par/exec-audit` → 5-gate 全过（typecheck 全绿 / lint 0 警 / 全量 1548 仅 bubblewrap 基线）→ push `a721a90c..89d2c04f`。
- **收口后**：`par/exec-audit` 已消费，勿在其上续开；新会话基于新 main `89d2c04f` 开 `par/*`。

## 🌊 Wave-3 并行分工（S1 下发，2026-09-02）

| 会话 | 分支 | 工作 | 依赖 |
| --- | --- | --- | --- |
| S2 domain | `par/domain-ssot` + cov2/cov3/kcov/refine/status | **SSOT `isTerminalRunStatus`** ✅ **已合入 main `006125b9`**；domain 纯测试补 5 批 — ✅ **M2 合入**（+720 用例/覆盖率） | 完成 |
| S5 runtime | `par/runtime-ssot` + `par/runtime-hardening` | SSOT 消费侧 ✅ `22360a67`；hardening（double-completion 修复 + SSOT cascade fix + 分支覆盖）— ✅ **M2 合入** | S2 已合 ✅ |
| S4 persistence | `par/persistence-clean3` | 包内整理 — ✅ **已合入 main**（in-memory/prod 对齐 S-A~S-H + EventBridge tests + db-open PG skip + cross-impl 线束扩） | 无 |
| S6 apps+cli | `par/api-clean3` | 包内整理 — ✅ **已合入 main M2**（env 去重共享 env-util + 删 7 死导出 + cli lint 门恢复 + exec-audit/CR/tool-profile/test 补覆盖） | 无 |

> **Wave-3 全部完成（M2 已收口 main `4a6e628f`）**。S2 纯测试 5 批与 S5 hardening 因完全独立一并在 M2 收口；S4 persistence 对齐 + S6 apps-cli 整理同步完成。

**当前主线（D49 exec 审计记账）**：owner 重定向——Channel Port 退役（只用微信）；S6 开 exec 行为审计记账；S2/S4/S5 各包"整理与完善"。Wave-2 前半（D48）与 S6 exec（D49）均已并入 main。已并入：
- **D48 / Wave-2 前半（整理类）**：S2 domain `9639d265`（schedule/quiet-reply 边界，vitest 314）、S4 persistence `e7f8a8ed`（修基线 project-knowledge-store.ts:120 exactOptionalPropertyTypes + 边界测试，vitest 108）、S5 runtime `de3da1e2`（终态原子审计 transitionRunToTerminal/withTransaction；denyWaitingStep 走守卫；去 3 处冗余 as；runtime+arch 379）。
- **D49 / S6 exec 审计记账 `22d6691f`**：apps/api 新 `exec-audit.ts`（ExecAuditContext + recordExecAudit 统一落库）；覆盖 workspace-tools（run_command/read_file/write_file 含 bwrap 回退）、mcp-spawn→mcp-bootstrap（spawned）、wechat/dev-quality-gate。事件 `exec.executed`。纯观测、不签发权限、副作用咽喉未变；audit await 修复 PGlite 竞态。10 files +265/−43。

**5-gate（S1 合并后复核）**：D48 3 包 lint 0 警 / 全量 252 pass；D49 lint apps 0 警 / 全量 **253 files / 1545 pass / 1 skip**。多次全量回归仅剩两类环境 fail（cli 符号链伪影、workspace-tools.bubblewrap 缺系统沙箱，均在共享 worktree/沙箱缺依赖，真实生产树正常），无一在本批改动文件。**typecheck 基线遗留已在 M1 分支 bc704b6a 清零**（含原 `apps/api/wechat-project-surface.ts:314`）。

**S1 决策登记**：1. domain `./tools/types.js` 仅 `_archive/contracts` 消费 → **保留**（兼容层，非生产路径）。2. **SSOT isTerminalRunStatus 立项**（Wave-3 协调项，S2+S1 共同提交，勿单会话）。

## 🎯 eval 场景超时韧性（已收口 2026-09-03）

- **根因**：多轮 eval 场景（05/14/15）每轮重建 PGlite+wiring（migrate ~700ms/轮），全量并行 CPU 争抢下超时；eval/14 是全量唯一不稳定 fail。
- **修复**：eval harness 新增 `makeEvalHarness`/`closeEvalHarness` + `RunScenarioInput.harness`，DB+wiring 建一次跨轮复用；`runEvalScenario` 仅在自有 DB 时 close。
- **效果**：eval/14 6.9s→~2.0s，setup 755ms/轮→0；eval/05 1.18s、eval/15 1.95s；所有 22 个 eval 场景 standalone PASS，typecheck+lint 绿。
- commit `e90609dd`（4 文件 +88/−20）。

## 🗑️ domain/workflows 死模块归档（已收口 2026-09-03）

- **处置**：`packages/domain/src/workflows/`（WorkflowState/WorkflowRun/workflowTransition/Channel 抽象）**无生产消费者**（仅 domain barrel 转发），DESIGN/Roadmap 明确 **WorkflowRun 不存在**、Task/Procedure MVP 以 task/procedure 表落地、渠道仅微信（无需多 Channel 抽象）。归档至 [`_archive/packages/domain/workflows/`]（ellet 现有 `_archive/packages/application/_archive/run-workflow` 同惯例）。
- **改动**：git mv → `_archive/packages/domain/workflows/`；`packages/domain/src/index.ts` 删 workflows barrel 转发。tsconfig include 仅 `packages/*/src`，vitest exclude `**/_archive/**` → 归档目录不参与编译/测试收集。
- **门禁**：typecheck 全绿 / deadcode 不再报 workflows / domain+arch 74 文件 580 用例全过 / lint 0 警。
- **遗留观察（未动）**：`packages/domain/src/tools/index.ts` 的 `isToolTimeout/sortToolsByPriority/validateToolDefinition/describeCommandSpec` 仅被自身 barrel+测试引用（ts-prune 报死），但属于 domain/tools 域内 API，需进一步核实后决定归档或保留——本次控制范围未动。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底
- 替未完成会话 commit 共享工作树 WIP（d89385ea 弃稿勿提交，已被 43f8a645/de3da1e2 接管）
- 造"第二实现"仅为可替换而硬物化 Memory/Channel Port

## 上一班

- 2026-09-03 (M3 收口)：审批恢复硬化验收——grant 过期/耗尽决策测试 + 跨重启恢复/重启后过期不恢复测试；bubblewrap slirp env 门控基线归零。5-gate 全过（全量 262/263，仅 eval/14 并行过载超时，单独跑通过）。
- 2026-09-03 (M2 收口)：S1 收口 8 ahead 分支到 main `4a6e628f`——S2 domain 纯测试 5 批 + S5 runtime-hardening + S4 persistence 对齐（S-A~S-H）+ S6 apps-cli 整理。5-gate：typecheck 全绿 / lint 0 警 / 全量回归 259/263（仅 bubblewrap + eval/scenarios 环境基线）。
- 2026-09-02 (SSOT 收口)：S1 合 S2 domain 侧 `006125b9` + S5 消费侧 `22360a67`——SSOT isTerminalRunStatus Wave-3 协调项关闭。domain 25/25、runtime+arch 65/379、全仓 typecheck 全绿。
- 2026-09-02 (M1 收口)：S1 合 `par/exec-audit` 入 main（`89d2c04f`）——exactOptionalPropertyTypes 基线清零 + 并行模型升级黑板。5-gate 全过。Wave-3 分工下发（SSOT S2+S1 / S4 / S6）。
- 2026-09-02 (M1 宣布)：并行模型升级落盘 + 首个汇聚点宣布。见 .blackboard/parallel/README.md。
- 2026-09-02 (D49)：S6 exec 行为审计记账并入（FF 22d6691f）。lint apps 0 警，全量 253/1545。typecheck 基线遗留未清（wechat-project-surface.ts:314）。
- 2026-09-02 (D48 Wave-2 前半)：S1 把关合并 S2 domain + S4 persistence + S5 runtime（整理类）。3 包 lint 0 警，全量仅 3 环境 fail。typecheck 基线 2→1。SSOT isTerminalRunStatus 立项（S2+S1 协调）。
- 2026-09-02 (D47)：见 .blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md。
- 2026-09-02 (D46)：Repository Port 物化（in-memory RuntimeStore + ports RepositoryPort；推 D26B §20 #6 原 lock）。
- 2026-09-02 (D45)：owner-routes 按域拆分 7 子模块。
