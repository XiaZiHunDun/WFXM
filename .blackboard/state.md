# WFXM BlackBoard State

_last_synced: 2026-09-02 (D47 并行 Wave-1 三会话合并)
_handoff: .blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md

**并行开发（2026-09-02 立项，见 `.blackboard/parallel/`）**：monorepo 按包边界长期并行。各会话开 `par/<area>` topic 分支，唯一在 main 的 **S1 编排会话**负责收口共享文件并合并。会话：S1 orchestration / S2 domain / S3 ports+adapters / S4 persistence / S5 runtime / S6 apps+cli。索引与各会话交接卡在 `.blackboard/parallel/`（README + s1-s6）。共享/承重文件（DESIGN/port-catalog/ports index/arch guard/state）仅 S1 可改。

**当前主线（D47 并行 Wave-1 合并）**：并行开发 Wave-1 三会话（S2 domain / S4 persistence / S5 runtime）经 S1 把关合并入 main。仅测试增强与运行时加固，**无签名/契约变更、未动 shared 承重文件**。逐分支 diff 核干净（各守包边界、互不重叠）→ 顺序 FF + `--no-ff` 收口。

- **S2 domain（`1daa740f`）**：`packages/domain/src/runtime/` 两测试文件增强——`transitions.test.ts` 8×8 RunStatus 全达矩阵（deadline/cancelled/waiting_approval 三分支；transitionRun 非法拒绝不 version-bump/不变异；terminal 自转拒绝）；`run-trigger.test.ts` full-run/parent-run 归一化边界（channel/webhook 强制 conversationRef，api/cli/schedule/task/parent_run 不强制；budget default override；task 条件性入 payload）。domain vitest 310。
- **S4 persistence（`3981845c`）**：新增 `packages/persistence/src/runtime-store.cross-impl.test.ts`——store 契约一致性线束，同一组断言同时跑 production `createRuntimeStore(PGlite)` 与 in-memory，证 Repository Port 可替换。18 测试。两实现 6 处行为差异（idempotencyKey 去重 / content 脱敏 / waiting-approval kind 门控 / listRunsPastDeadline 状态门控 / findChildRuns 排序 / findActiveGrant digest）以生产为准，in-memory 注明简化。
- **S5 runtime（`43f8a645`）**：`run-lifecycle.ts` 新增 `transitionRunToTerminal` 双重完成守卫 + 修复 `expireOverdueRuns` 并发跳过（catch 重读，终态跳过继续，sweep 幂等）；`run-engine.ts` finalize 走守卫、tracer finalStatus 改真实终态。+10 用例。运行时完成（成功）/失败暂不写 audit（范围决策待定）。

**5-gate（S1 在合并后 main 复核）**：3 包 lint 0 警 / 全量 `CI= pnpm test` **254 files pass / 1536 pass / 1 skip，唯一 fail 为 cli worktree 符号链伪影**（`@hono/node-server` 相对链断裂，非本批改动，真实树正常）/ typecheck 仅剩 2 个**基线** exactOptionalPropertyTypes 错误（`apps/api/wechat-project-surface.ts`、`persistence/project-knowledge-store.ts`，非本批引入）。

⚠️ **基线遗留**（非本批、需合流会话/后续处理）：typecheck 有两个 exactOptionalPropertyTypes 错误在 main 基线已存在（wechat-project-surface.ts + project-knowledge-store.ts，源自 4d06ceb3 等）。

**下一步**：Wave-2 候选——S3 Channel Port（等 Slack/Telegram 真接生产）、S6 exec 记账（owner 确认后）。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底
- 替未完成会话 commit 共享工作树里的 WIP（run-lifecycle/run-engine 残留为 d89385ea 弃稿，已被 43f8a645 接管，勿提交）
- 造"第二实现"仅为证明可替换而硬物化 Memory/Channel Port（Repository 是由真实 in-memory 需求触发）

## 上一班

- 2026-09-02 (D47 并行 Wave-1)：S1 把关合并 S2 domain(状态机全表补测/契约冻结) + S4 persistence(cross-impl 契约线束) + S5 runtime(双重完成守卫/deadline 并发修复)。FF+no-ff 收口，lint 0 警，全量回归仅 cli 符号链伪影 fail。三分支已删（并入 main）。
- 2026-09-02 (D46 Repository Port)：业主选"推进 Repository Port（方式 A，先造触发条件）"。in-memory RuntimeStore + ports Repository Port + 3 arch guard + DESIGN/port-catalog 同步；推 D26B #6 原 lock；typecheck/lint/全量回归全绿。
- 2026-09-02 (D45 owner-routes 拆分)：按域拆 7 子模块 + 聚合入口 24 行；共享 memory-dedup helper；4 arch guard 改扫子模块源码；typecheck/lint/arch/主测试全绿。