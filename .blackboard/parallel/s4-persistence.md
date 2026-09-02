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

- D47 无两存冲突；如需 backfill / 事件桥适配由本会话排期。改 store 契约前先 @S2/@S1。