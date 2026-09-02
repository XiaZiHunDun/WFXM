# D47 并行 Wave-1 交接卡（S1）

> 时间：2026-09-02 · 分支：均已并入 main（`2f5068ba`）· 前置：D46 Repository Port 物化

## 一句话

并行开发 Wave-1 三会话经 S1 把关合并入 `origin/main`；仅测试增强与运行时加固，**无签名/契约变更、未动 shared 承重文件**；5-gate 复核通过（唯一 fail/cli 为 worktree 符号链伪影 + 2 个基线 typecheck 遗留）。

## 合并内容（按并入序）

| 会话 | commit | 改动 | 说明 |
| --- | --- | --- | --- |
| S2 domain | `1daa740f` | `run-trigger.test.ts` +90、`transitions.test.ts` +142/−29 | 8×8 RunStatus 全达矩阵 + trigger 归一化边界；契约冻结（无签名改动） |
| S4 persistence | `3981845c` | `runtime-store.cross-impl.test.ts` +461 | cross-impl 契约一致性线束（postgres ∪ in-memory），6 处简化差异上报 |
| S5 runtime | `43f8a645` | `run-engine.ts`/`run-lifecycle.ts` 等 4 文件 +10 用例 | `transitionRunToTerminal` 双重完成守卫；`expireOverdueRuns` 并发修复；sweep 幂等 |

合并方式：`par/domain` FF → `par/persistence` `--no-ff` → `par/runtime` `--no-ff`（串联两个同父分支需合并提交；文件互不相交，自动合并干净）。

## 5-gate 复核（S1 在合并后 main 执行）

- 逐分支 diff 核：各守包边界、路径互不重叠、无 shared 文件、domain 零签名改动。✅
- lint（3 改动包）：0 告警。✅
- 全量 `CI= pnpm test`：254 files pass / 1536 pass / 1 skip；**唯一 fail = `cli/src/index.test.ts` 的 `@hono/node-server` load 失败——worktree 里相对符号链断裂的环境伪影，文件 `cli/src/index.ts` 非本批改动，真实树正常**。✅（判定非回归）
- typecheck：仅 2 个**基线** exactOptionalPropertyTypes 错误（详见下）。本批未新增。✅

## 基线遗留（⚠️ 非本批，供后续会话/合流）

1. `apps/api/src/wechat-project-surface.ts:314` — `mcpBundle: McpToolBundle | undefined` 传给 `mcpBundle?` 可选参数（exactOptionalPropertyTypes 需显式处理 undefined）。
2. `packages/persistence/src/project-knowledge-store.ts:120` — `limit: number | undefined` → `limit?`。

两者均源自 main 已有提交（4d06ceb3 等），与本批无关；处理时确认归属会话再动。

## 写给其它会话 / 新会话

- **别重复已做**：domain 状态机全表、Repository cross-impl 线束、deadline 双重完成守卫均为已完成（main）。
- **共享工作树卫生**：共享 checkout 现存 S5 弃稿残留（`run-engine.ts` / `run-lifecycle.ts` 等 4-5 个文件为 d89385ea 内容，已被 `43f8a645` 接管）——**勿提交**；如需清理可在安全时 `git checkout origin/main -- packages/runtime/...` 或 `git clean` 前先问 S1。
- **三分支已并入并清理**：`par/domain`、`par/persistence`、`par/runtime` 为已消费 topic，勿在其上续开（回到这些 topic 前先 rebase 到新 main）。

## 下一步候选（Wave-2）

- S3 Channel Port — 等 Slack/Telegram 真接生产信号（DESIGN §7 禁造休眠接口）。
- S6 exec 记账 — owner 确认真实诉求后再开。
- 2 个基线 typecheck 遗留 — 归口合流会话或 S1 领衔排期。

## S1 操作记录

- 并入提交：`1daa740f`（FF）→ `80f4a340`（merge persistence）→ `2f5068ba`（merge runtime）。
- 推送：`03e42904..2f5068ba main`。
- 黑板：`state.md` 更新 + 本卡。