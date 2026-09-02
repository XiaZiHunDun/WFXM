# S4 — persistence 会话（存储/迁移/事件签发）

**职责**：负责 `packages/persistence/**`——store 实现、数据库迁移（`migrations/0001_initial.sql`）、增量/回填、事件桥。仓储/事件/outbox 的落库侧。

## 独占路径

- `packages/persistence/**`（含 `runtime-store.ts`、`memory/`；**任何新 DB 实现在包内新建**）
- 数据库 schema（`packages/persistence/src/migrations/*.sql`）

## 边界（不可动）

- 不改 `packages/ports/**`（`index.ts`/barrel——归 S1；不改 ports/core 内已有端口）。
- **依赖方向**：persistence 只 import `domain`（先例即如此）。**禁止** import `ports / runtime / apps`（守 arch guard）。
- 不改其它包实现 / `.blackboard` / `DESIGN.md` / `port-catalog.md`。
- 生产 schema 认证口径：`0001_initial.sql` 是唯一生产真相（D-series 规则）。加列/建表改迁移与对应 store 单测。

## 依赖/上游

- 依赖 S2（domain 契约）。为 S5/S6 提供 `createRuntimeStore` / 事件落库。
- 与 S3 若需协同（如事件桥复用端口），先经 S1 登记，避免各自改公共面。

## 常规先手

- `memory/runtime-store.ts`（in-memory 第二实现，D46 已建）——可作为纯落库逻辑替代与快速单测载体；若改它，注意同步 `packages/persistence/src/index.ts` 导出。
- 新迁移：`migrations/0001_initial.sql` 追加（或新增 `0002_*.sql`，按现有迁移编号规约）+ 对应 store 变更 + 单测。

## 最小门禁（提交前）

```bash
cd butler-v5/packages/persistence && pnpm exec tsc --noEmit
cd butler-v5 && CI= pnpm exec vitest run packages/persistence tests/architecture/section7-1-repository -q
pnpm exec eslint packages/persistence --ext .ts --max-warnings 0
```

## 当前相关待办

> ⚠️  **历史待办**：以下 Wave-3 任务已在 M2（main `4a6e628f`）全部收口完成，本段仅作归档留底。
>  ✅ 实际完成见末尾「M2 收口摘要」。

- **Wave-3 包内整理与完善（S4，2026-09-02 业主确认）**：persistence 包内自查自净，**只动包内、不碰共享文件**。候选方向（择真实存在者做，勿虚构）：
  - **store 一致性核对**：`memory/runtime-store.ts`（in-memory 第二实现）与 production `runtime-store.ts` 的 6 处已知行为差异（D47 记录：idempotencyKey 去重 / content 脱敏 / waiting-approval kind 门控 / listRunsPastDeadline 状态门控 / findChildRuns 排序 / findActiveGrant digest）——逐项确认是"简化"还是"应补齐"；若应补，加注释 + 单测锁行为。
  - **测试补强**：`db-open.test.ts` 依赖真实 postgres（沙箱 fail）——评估能否用 PGlite 或 in-memory 补一个不依赖外部 DB 的路径测试（不改生产语义，仅测试基建）。
  - **文件行数**：`runtime-store.ts` 582 行、`durable-memory-store.ts` 341 行——无阻塞，但可评估合理拆分（遵守 G6 >800 才需拆；**不要为拆而拆**）。
  - **导出面核对**：`packages/persistence/src/index.ts` 是否有未用导出 / 命名不一致（对照 domain 契约消费方）。
- D47 无两存冲突；如需 backfill / 事件桥适配由本会话排期。改 store 契约前先 @S2/@S1。
---

## ✅ M2 收口摘要（已并入 main `4a6e628f` via `par/persistence-clean3`）

- **in-memory/production RuntimeStore 对齐**：S-A~S-H（idempotencyKey 去重、kind==='approval' 门控、ACTIVE_MAIN_RUN_STATUSES 死端门控、排序、findActiveGrant digest 语义等 8 项补齐）。
- **测试基建扩**：新增 `event-bridge.test.ts`；`db-open.test.ts` PG server 不可达时 skip；`runtime-store.cross-impl.test.ts` 契约线束扩 +460 行。
- **5-gate**：persistence tsc ✓、lint 0 警、全测试 PASS。
