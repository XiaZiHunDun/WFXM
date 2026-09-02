/**
 * Repository Port — runtime 状态持久化读写的接缝（DESIGN §7 表 Repository 行）。
 *
 * D46 物化（方式 A：先造触发条件再物化）。触发 = **第二持久化实现**：
 * 生产 `createRuntimeStore`（Drizzle + postgres/PGlite）之外新增
 * `createInMemoryRuntimeStore`（`packages/persistence/src/memory/runtime-store.ts`，
 * 纯内存、无 DB/IO）。两个实现都实现同一份 `RuntimeStore` 合同，证明它是一条
 * 可替换的单一接缝（Repository Port），满足 DESIGN §7"真正的可替换边界才设 Port"
 * 与"不预先为架构完整造休眠接口"。
 *
 * 形态：`RepositoryPort` **复用 domain 的 RuntimeStore 合同**（单一真相源，
 * 不重复声明 20 个方法）。ports 层只声明端口归属 + 收敛类型导出，interface-only，
 * 0 class / 0 impl / 0 IO（满足 D31 §7 thin-barrel + interface-only + 依赖方向
 * 向内：ports → domain）。
 *
 * 两个 adapter：
 *   - `packages/persistence/src/runtime-store.ts`（Drizzle/postgres，生产）
 *   - `packages/persistence/src/memory/runtime-store.ts`（in-memory，测试/隔离）
 *
 * 消费侧：`apps/api`、`packages/runtime` 经 `RuntimeStore` 类型注入
 * Composition Root wiring；schema 变更由本 Port 隔在 core 之外（DESIGN §3）。
 */
import type { RuntimeStore } from "@butler/domain/runtime.js"

/**
 * Repository Port — runtime 状态（Conversation / Message / Run / Step /
 * Grant / Audit）的读与写边界。替换实现 = Drizzle-postgres runtime-store 或
 * in-memory runtime-store，由 Composition Root 注入。
 */
export type RepositoryPort = RuntimeStore

export type { RuntimeStore }
