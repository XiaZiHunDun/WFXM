# D45 — owner-routes.ts 拆分（2026-09-02）

**批次**：D45 · 主线：apps/api/src（owner 控制面）· 语言：TS

**目标**：消除 typecheck-gate file-size BLOCK（`owner-routes.ts` 1262>1200 既有状态）。拆分是纯结构性重构，行为零变化。

## 交付（聚合入口 + 7 子模块 + 共享 helper + 4 arch guard 改写）

| 文件 | 内容 |
| --- | --- |
| `apps/api/src/owner-routes.ts` | 降为聚合入口（24 行），`createOwnerRoutes` 依次调 7 个 `register<Domain>Routes` |
| `owner-routes/conversations-schedule.ts` | conversations ×2 + schedule/tick |
| `owner-routes/approvals-runs.ts` | approvals ×3 + runs cancel/expire-overdue |
| `owner-routes/memories.ts` | memories GET/POST/confirm/reject/rollback/delete/confirm-batch/reject-batch + `parseBatchIds`/`handleBatch` |
| `owner-routes/documents.ts` | documents 全量 + promote-memory + promote-project-knowledge + cascade delete |
| `owner-routes/project-knowledge.ts` | 4 routes + manifest sync |
| `owner-routes/traces-procedures-tasks.ts` | traces/procedures/tasks |
| `owner-routes/mcp.ts` | mcp/status + revoke-grants |
| `owner-routes/memory-dedup.ts` | `makeDedupChecker()`（G2 dedup 共享，memories + documents promote-memory 共用，module-scoped env 语义不变） |
| `tests/architecture/owner-routes-source.ts` | `readOwnerRoutesSource()` 拼接聚合入口 + 子模块，供 arch guard 用 |

## 关键决策

- 内嵌 helper（`parseBatchIds`/`handleBatch`/`checkDedup`/`dedupCfg`/`autoPromoteCfg`）随 memories 域移动；`checkDedup` 抽共享模块供 documents promote-memory 复用
- 每个子模块独立 import（hono Wiring/owner-auth/各 helper），不 import 原 owner-routes 防循环
- 4 个 arch guard（section11/12/18/child-run-cancel-cascade）原 readFileSync 单扫源码，改经 `readOwnerRoutesSource()` 扫全路由源码，静态 lock 意图（端点存在性 / cancelRunCascade / hasMore / countBySubject）不变

## 5-gate

typecheck 全包 PASS / lint 0 警 / arch guard 216 PASS / **file-size 门禁 PASS（不再报 owner-routes.ts）** / 主测试 `CI= pnpm test` **252 files / 1480 pass / 1 skip / 0 fail**（与 D44 基线一致，无 db-open 实连依赖）。

## 下一步

push origin/main。后续 batch 候选（D46 起）：exec 记账（owner 真撞）、Repository Port（等第二持久化实现）、Channel Port（等 Slack/Telegram 真接生产）。
