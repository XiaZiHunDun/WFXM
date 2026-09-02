# WFXM BlackBoard State

_last_synced: 2026-09-02 (D49 exec 审计记账并入；D48 Wave-2 前半已并)
_handoff: .blackboard/shifts/2026-09-02-d49-exec-audit-handoff.md

**并行开发（2026-09-02 立项，见 `.blackboard/parallel/`）**：monorepo 按包边界长期并行。各会话开 `par/<area>` topic 分支，唯一在 main 的 **S1 编排会话**负责收口共享文件并合并。会话：S1 / S2 domain / S3 ports+adapters（已退役主任务）/ S4 persistence / S5 runtime / S6 apps+cli。共享/承重文件（DESIGN/port-catalog/ports index/arch guard/state）仅 S1 可改。

**当前主线（D49 exec 审计记账）**：owner 重定向——Channel Port 退役（只用微信）；S6 开 exec 行为审计记账；S2/S4/S5 各包"整理与完善"。Wave-2 前半（D48）与 S6 exec（D49）均已并入 main。已并入：
- **D48 / Wave-2 前半（整理类）**：S2 domain `9639d265`（schedule/quiet-reply 边界，vitest 314）、S4 persistence `e7f8a8ed`（修基线 project-knowledge-store.ts:120 exactOptionalPropertyTypes + 边界测试，vitest 108）、S5 runtime `de3da1e2`（终态原子审计 transitionRunToTerminal/withTransaction；denyWaitingStep 走守卫；去 3 处冗余 as；runtime+arch 379）。
- **D49 / S6 exec 审计记账 `22d6691f`**：apps/api 新 `exec-audit.ts`（ExecAuditContext + recordExecAudit 统一落库）；覆盖 workspace-tools（run_command/read_file/write_file 含 bwrap 回退）、mcp-spawn→mcp-bootstrap（spawned）、wechat/dev-quality-gate。事件 `exec.executed`。纯观测、不签发权限、副作用咽喉未变；audit await 修复 PGlite 竞态。10 files +265/−43。

**5-gate（S1 合并后复核）**：D48 3 包 lint 0 警 / 全量 252 pass；D49 lint apps 0 警 / 全量 **253 files / 1545 pass / 1 skip**。多次全量回归仅剩两类环境 fail（cli 符号链伪影、workspace-tools.bubblewrap 缺系统沙箱，均在共享 worktree/沙箱缺依赖，真实生产树正常），无一在本批改动文件。**typecheck 基线遗留仍 1 个**：`apps/api/wechat-project-surface.ts:314` exactOptionalPropertyTypes（S6 报告 tsc PASS 但未清，非本批引入）。

⚠️ **基线遗留（未清，需 owner 定夺）**：`apps/api/src/wechat-project-surface.ts:314`。归 S6 已明确但未执行。可选处置：S1 顺手修（apps 生产代码、非 S1 独有）/ S6 补 / 留待。

**S1 决策登记**：1. domain `./tools/types.js` 仅 `_archive/contracts` 消费 → **保留**（兼容层，非生产路径）。2. **SSOT isTerminalRunStatus 立项**（Wave-3 协调项，S2+S1 共同提交，勿单会话）。

**下一步**：**Wave-3 协调项 SSOT isTerminalRunStatus**（S2 domain `runtime/transitions.ts` 由 LEGAL_TRANSITIONS 无出边导出 + barrel，S5 消费删本地 `TERMINAL_RUN_STATUSES`；S2+S1 共同提交）。可选：MemoryService（§12）物化触发；清 `wechat-project-surface.ts:314` 遗留。并行开发基本收敛，无在途长尾会话。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底
- 替未完成会话 commit 共享工作树 WIP（d89385ea 弃稿勿提交，已被 43f8a645/de3da1e2 接管）
- 造"第二实现"仅为可替换而硬物化 Memory/Channel Port

## 上一班

- 2026-09-02 (D49)：S6 exec 行为审计记账并入（FF 22d6691f）。lint apps 0 警，全量 253/1545。typecheck 基线遗留未清（wechat-project-surface.ts:314）。
- 2026-09-02 (D48 Wave-2 前半)：S1 把关合并 S2 domain + S4 persistence + S5 runtime（整理类）。3 包 lint 0 警，全量仅 3 环境 fail。typecheck 基线 2→1。SSOT isTerminalRunStatus 立项（S2+S1 协调）。
- 2026-09-02 (D47)：见 .blackboard/shifts/2026-09-02-d47-parallel-wave1-handoff.md。
- 2026-09-02 (D46)：Repository Port 物化（in-memory RuntimeStore + ports RepositoryPort；推 D26B §20 #6 原 lock）。
- 2026-09-02 (D45)：owner-routes 按域拆分 7 子模块。
