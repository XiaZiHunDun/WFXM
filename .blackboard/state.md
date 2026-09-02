# WFXM BlackBoard State

_last_synced: 2026-09-02 (D45 owner-routes 拆分)
_handoff: .blackboard/shifts/2026-09-02-d45-owner-routes-split-handoff.md

**当前主线（D45 owner-routes.ts 拆分）**：消除 typecheck-gate file-size BLOCK（1262>1200 既有状态）。`owner-routes.ts` 降为聚合入口（24 行），路由实现按域拆入 `apps/api/src/owner-routes/` 7 子模块：conversations-schedule / approvals-runs / memories / documents / project-knowledge / traces-procedures-tasks / mcp，各自导出 `register<Domain>Routes(app, wiring)`；`checkDedup` 抽为共享 `memory-dedup.ts`（memories + documents promote-memory 共用），`dedupCfg/autoPromoteCfg` 保持 module-scoped env 语义。行为零变化。

**内容**：4 个 arch guard（section11/12/18/child-run-cancel-cascade）原先 readFileSync 单扫 `owner-routes.ts` 源码做静态 lock，改为经共享 helper `tests/architecture/owner-routes-source.ts` 拼接聚合入口 + 全部子模块源码，guard 意图（端点存在性 / cancelRunCascade 等）不变。

**5-gate**：typecheck 全包 PASS / lint 0 警 / 主测试 **252 files / 1480 PASS / 1 skip / 0 fail**（`CI= pnpm test` 全量回归，与 D44 基线一致）/ arch guard 216 PASS。**file-size 门禁不再报 owner-routes.ts**（`bash scripts/typecheck-gate.sh` file-size: PASS）。

**下一步**：已按 D-series 审核 commit + push origin/main。后续 batch 候选（D46 起）：exec 记账（若 owner 真撞）、Repository Port（等第二持久化实现）、Channel Port（等 Slack/Telegram 真接生产）。

## 不要做

- 改 `wechat-inbound-butler.ts`
- live smoke 升格 PR 硬门槛
- R17 起 v5 AI guard hook 已退役；承重文件改动走 commit review + 5 gate 兜底

## 上一班

- 2026-09-02 (D45 owner-routes 拆分)：业主选"拆 owner-routes.ts（推荐）"。按域拆 7 子模块 + 聚合入口 24 行；共享 memory-dedup helper；4 arch guard 改扫子模块源码；typecheck/lint/arch/主测试全绿，file-size 门禁闭环。
