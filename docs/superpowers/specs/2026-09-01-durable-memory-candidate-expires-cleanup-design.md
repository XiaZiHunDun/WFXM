# Durable Memory Candidate Expires Cleanup — 设计 spec (G1)

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-01-durable-memory-candidate-expires-cleanup.md`（plan 阶段产出）。
> **背景**：D39 §12 G3 batch candidate UI 已 ship (`47b97352`)。owner 撞的下个痛点是 candidate 堆积后无 owner 处理的 stale candidate 持续占库。本 spec 实施 G1 expires cleanup — candidate 7 天未被 confirm/reject 自动转为 status=`expired`（soft delete）。
> **优先级**：G1 expires cleanup；其余 G2 dedup / G4 Layer 1→2 auto-promote / G5 跨 project PK recall 留待下轮。
> **影响面**：`packages/persistence` 加 `listExpiredCandidates` + `markExpired` 2 能力；`packages/domain/src/knowledge/candidate-expires.ts` 新文件（pure fn）；`apps/api/src/candidate-expires-sweeper.ts` 新文件（opt-in 同进程 timer）；`DurableMemoryStatus` enum 加 `'expired'`；D30 §12 arch guard 加 1 case。

---

## 1. 目标

解决 owner "candidate 多到处理不动" 后续残留问题 — stale candidate 7 天后自动软删除，让 §12 durable_memories 表保持 owner 工作流的可管理状态：

1. **Soft delete via status**：candidate 7 天未被 owner 处理 → `status='expired'`，row 保留（owner 可查历史 / unexpire）；不破坏 §12 "可追溯 Message/Document/Owner" 语义
2. **Pure domain + persistence pair**：核心逻辑 `expireOldCandidates` 在 domain 层为纯函数；persistence 提供 `listExpiredCandidates` + `markExpired` 2 能力；不引入新 Core Port
3. **Opt-in 同进程 sweeper**：`apps/api/src/candidate-expires-sweeper.ts` 复用 schedule-worker opt-in 模式（env-gated + setInterval）；不创建第二套 Loop / Policy / 独立进程（§20 #11 + §18 #11 不默认建设）
4. **§12 D30 lock 延伸**：`'expired'` 是合法 `DurableMemoryStatus`；arch guard 加 1 case lock
5. **0 first-class event 新增**：沿用 logger；trace 走现有 §14 observability 不变

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| Scope | 仅 `status='candidate'` 过期；confirmed 不动 |
| TTL | 7 天（`createdAt` < now - 7d） |
| Action | Soft delete：`status='candidate'` → `status='expired'`；row 保留 |
| Schedule 路径 | 独立同进程 sweeper（`apps/api/src/candidate-expires-sweeper.ts`）；不走 Schedule.RunTrigger（无 LLM）；不复用 schedule-worker job type（避免 refactor LLM-bound `runScheduleJob`） |
| 默认配置 | opt-in（`BUTLER_V5_CANDIDATE_EXPIRES_ENABLED=1` 才启动）；tickMs=1h；ttlMs=7d |
| Schema | `DurableMemoryStatus` 加 `'expired'`（成 4 member: `candidate`/`confirmed`/`rejected`/`expired`）；`createDurableMemoryRecord` validation allowlist 仍只 accept `candidate`/`confirmed`/`rejected` 写路径 |
| First-class event | 0 新增；logger.info 走现有 operator log（与 schedule-worker 同模式） |
| Arch guard | D30 §12 suite 扩 1 case：`'expired'` 合法 status |
| 推下轮 | G2 dedup / G4 Layer 1→2 auto-promote / G5 跨 project PK recall |

---

## 3. 现状与不一致

### 3.1 已 ship（D39 闭环后）

- §12 durable_memories 表 + `DurableMemoryRecord` 4 字段（`sourceKind` / `confidence` / `expiresAt` / `status`）— D30 lock case #2
- G3 batch candidate UI：owner routes confirm-batch / reject-batch + wechat `/记忆候选` + `/确认记忆` 扩面 — D39 ship
- `DurableMemoryStatus` enum = `'candidate' | 'confirmed' | 'rejected'`（D30 lock + D39 owner-route guard；'rejected' 由 `rejectDurableMemory` 写路径使用）
- §20 #11 lock：schedule 不创建第二套 Loop / Policy
- §11.4 + §18 #11 不默认建设 — broker / 独立 worker 缺实测触发

### 3.2 真缺（1 gap）

- **stale candidate 无生命周期**：candidate 7 天后仍未被 owner confirm/reject 仍占表；owner 撞 "candidate 多到处理不动" 之后 stale 持续堆积；§12 schema `expiresAt` 字段已存在但 lifecycle 无 job 触发

### 3.3 文档 drift

- 无 doc drift；本 spec 实施后 §18 row 3 / §11 row 5 / §12 audit state 三处 note 保留 MVP ship 状态；G1 不改任何 §段 status

### 3.4 Persistence 缺口

- `DurableMemoryStore` 无 `listExpiredCandidates({olderThan})` 方法
- `DurableMemoryStore` 无 `markExpired(ids[])` 方法
- 不改 `listBySubject` / `countBySubject` / `confirmDurableMemory` / `rejectDurableMemory` 现有方法（D39）

---

## 4. 设计

### 4.1 Persistence 扩展（1 文件 + 1 test）

`butler-v5/packages/persistence/src/durable-memory-store.ts`：

```ts
// 新增方法 1：列过期 candidate
listExpiredCandidates(opts: {
  readonly olderThanMs: number;   // now - ttlMs
  readonly limit?: number;        // default 1000（防一次扫太多）
}): Promise<readonly { id: string; createdAt: Date }[]>

// 新增方法 2：批量标 expired（只在 status='candidate' 时更新，幂等）
markExpired(ids: readonly string[]): Promise<readonly { id: string; updated: boolean }[]>
```

**SQL 等价**：
```sql
-- listExpiredCandidates
SELECT id, created_at FROM durable_memories
WHERE status = 'candidate' AND created_at < $1
ORDER BY created_at ASC
LIMIT $2;

-- markExpired (per-id UPDATE 保证幂等；affected 0 = already expired/rejected/concurrent)
UPDATE durable_memories
SET status = 'expired', updated_at = NOW()
WHERE id = $1 AND status = 'candidate'
RETURNING id, (updated_at = created_at) AS updated;
```

**幂等性**：`markExpired` UPDATE 谓词 `status='candidate'` — 已 expired/confimed/rejected 的 row 不更新；并发场景安全。

**测试**（`durable-memory-store.test.ts` 新增 ~6 cases）：
- `listExpiredCandidates` 0 条 / 1 条 / N 条 / limit 边界 / 不含 confirmed
- `markExpired` 0 affected / 1 affected / N affected / 已 expired 不重标 / 已 confirmed 不动

### 4.2 Domain 纯函数（1 文件 + 1 test）

`butler-v5/packages/domain/src/knowledge/candidate-expires.ts`（新文件）：

```ts
import type { DurableMemoryStore } from "@butler/persistence/durable-memory-store.js"

export interface ExpireOldCandidatesInput {
  readonly store: DurableMemoryStore
  readonly now: Date
  readonly ttlMs: number            // default 7 * 24 * 3600 * 1000
  readonly batchLimit?: number      // default 1000
}

export interface ExpireOldCandidatesResult {
  readonly scanned: number
  readonly expired: number
  readonly olderThanMs: number
}

/**
 * Pure function: list candidate rows older than now-ttlMs, mark them expired.
 * No side effects beyond the store; no clock coupling (now passed in).
 * Caller owns logger / error handling.
 */
export async function expireOldCandidates(
  input: ExpireOldCandidatesInput,
): Promise<ExpireOldCandidatesResult> {
  const batchLimit = input.batchLimit ?? 1000
  const olderThanMs = input.now.getTime() - input.ttlMs
  const candidates = await input.store.listExpiredCandidates({
    olderThanMs,
    limit: batchLimit,
  })
  const ids = candidates.map((c) => c.id)
  if (ids.length === 0) {
    return { scanned: 0, expired: 0, olderThanMs }
  }
  const results = await input.store.markExpired(ids)
  const expired = results.filter((r) => r.updated).length
  return { scanned: ids.length, expired, olderThanMs }
}
```

**架构不变量遵守**：
- §20 #2: 接受 `store` 参数（依赖倒置），不 import 具体 adapter
- §20 #3: 副作用仅 DB UPDATE（不是 LLM / 外发）；不发 outbox
- §3 #4: Governance SDK-isolated — 不调 policy / grant / approver
- §20 #11: 不是 Schedule.RunTrigger；不创建 Loop

**测试**（`candidate-expires.test.ts` 新增 ~5 cases）：
- 7-day 边界（just over / just under）
- 空 list → scanned=0, expired=0
- 标 N 条 → expired=N, scanned=N
- 部分已 expired（idempotent）→ scanned=N, expired=M<N
- `markExpired` 抛错 → propagate；sweeper 负责 catch

### 4.3 同进程 Sweeper（1 文件 + 1 test）

`butler-v5/apps/api/src/candidate-expires-sweeper.ts`（新文件）：

```ts
/**
 * Opt-in in-process candidate expires sweeper.
 * Same pattern as schedule-worker: env-gated, setInterval, logger, no second Loop.
 */
import { expireOldCandidates } from "@butler/domain/knowledge/candidate-expires.js"
import type { Wiring } from "./wiring.js"

export type CandidateExpiresLogger = {
  readonly info: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type CandidateExpiresSweeperHandle = {
  readonly stop: () => void
}

export interface CandidateExpiresSweeperConfig {
  readonly enabled: boolean
  readonly tickMs: number            // default 3600_000 (1h)
  readonly ttlMs: number             // default 7 * 24 * 3600 * 1000 (7d)
  readonly batchLimit?: number       // default 1000
}

export function parseCandidateExpiresSweeperConfig(
  env: NodeJS.ProcessEnv,
): CandidateExpiresSweeperConfig {
  return {
    enabled: env.BUTLER_V5_CANDIDATE_EXPIRES_ENABLED === "1",
    tickMs: parsePositiveIntMs(env.BUTLER_V5_CANDIDATE_EXPIRES_INTERVAL_MS, 3_600_000),
    ttlMs: parsePositiveIntMs(env.BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS, 7 * 24 * 3_600_000),
    batchLimit: parsePositiveInt(env.BUTLER_V5_CANDIDATE_EXPIRES_BATCH_LIMIT, 1000),
  }
}

const defaultLogger: CandidateExpiresLogger = {
  info: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log
    console.error(msg, ...args)
  },
}

export interface SweeperTickDeps {
  readonly wiring: Wiring
  readonly ttlMs: number
  readonly batchLimit?: number
  readonly now?: () => Date
  readonly logger?: CandidateExpiresLogger
}

/**
 * Single tick — pure data path; errors are caught and logged; sweeper keeps running.
 * Exported for tests.
 */
export async function runCandidateExpiresTick(
  deps: SweeperTickDeps,
): Promise<{ scanned: number; expired: number }> {
  const logger = deps.logger ?? defaultLogger
  try {
    const result = await expireOldCandidates({
      store: deps.wiring.durableMemoryStore,
      now: deps.now?.() ?? new Date(),
      ttlMs: deps.ttlMs,
      batchLimit: deps.batchLimit,
    })
    logger.info(
      `[candidate-expires] scanned=${result.scanned} expired=${result.expired} olderThanMs=${result.olderThanMs}`,
    )
    return { scanned: result.scanned, expired: result.expired }
  } catch (err) {
    logger.error(
      "[candidate-expires] tick failed:",
      err instanceof Error ? err.message : String(err),
    )
    return { scanned: 0, expired: 0 }
  }
}

/**
 * Opt-in entry point. Returns null when disabled. Pattern matches startScheduleWorkerIfEnabled.
 */
export function startCandidateExpiresSweeperIfEnabled(args: {
  readonly wiring: Wiring
  readonly env?: NodeJS.ProcessEnv
  readonly config?: CandidateExpiresSweeperConfig
  readonly logger?: CandidateExpiresLogger
}): CandidateExpiresSweeperHandle | null {
  const env = args.env ?? process.env
  const config = args.config ?? parseCandidateExpiresSweeperConfig(env)
  if (!config.enabled) return null

  const logger = args.logger ?? defaultLogger
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async (): Promise<void> => {
    if (stopped) return
    await runCandidateExpiresTick({
      wiring: args.wiring,
      ttlMs: config.ttlMs,
      batchLimit: config.batchLimit,
      logger,
    })
    if (!stopped) {
      timer = setTimeout(() => {
        void tick()
      }, config.tickMs)
    }
  }

  logger.info(
    `[candidate-expires] sweeper started tickMs=${config.tickMs} ttlMs=${config.ttlMs}`,
  )
  void tick()

  return {
    stop: () => {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
  }
}
```

**架构不变量遵守**：
- §20 #11: 不是第二套 Loop / Policy / Engine — 单 setInterval + pure domain fn
- §18 #11: 同进程，不建独立 worker
- §3 #4: 不调 grant / approver / policy

**测试**（`candidate-expires-sweeper.test.ts` 新增 ~6 cases）：
- `parseCandidateExpiresSweeperConfig` env 三 key 解析 + default
- env-gated off → `startCandidateExpiresSweeperIfEnabled` 返回 null
- env-gated on → start + tick 触发 `runCandidateExpiresTick`
- tick error → logger.error + next tick 仍 fire
- `stop()` → 不再 fire tick
- `runCandidateExpiresTick` 直接调用 → 调 store + 返结果

### 4.4 Wiring 接入（1 line）

`butler-v5/apps/api/src/server.ts`（或 `wiring.ts`）启动时：

```ts
import { startCandidateExpiresSweeperIfEnabled } from "./candidate-expires-sweeper.js"
// ... existing startup
startCandidateExpiresSweeperIfEnabled({ wiring, env })
```

不影响现有 schedule-worker（两个 worker 独立运行，独立 env gate）。

### 4.5 Schema 改动（enum 扩 1 值）

`butler-v5/packages/domain/src/knowledge/durable-memory.ts`：

```ts
// 修改
export type DurableMemoryStatus = "candidate" | "confirmed" | "rejected" | "expired"
```

**影响面**：
- owner-routes guard（D39）：`if (status === "rejected") return 409` — 加 1 case：`if (status === "expired") return 409`（已 expired 不能 re-confirm）
- repo write path（confirm / reject）：仍只 accept `candidate` → `confirmed` / `rejected`；不写 expired（只有 sweeper 写）
- 现有 5 owner-routes 测试不受影响（owner 不会主动 expire 任何东西）

### 4.6 Arch guard 调整

`butler-v5/tests/architecture/section12-knowledge-memory.test.ts` 加 1 case（保留 D30 6 cases + D39 G3 实证 case）：

```ts
test("§12 DurableMemoryStatus accepts 'expired' (G1 candidate expires cleanup)", () => {
  // 验证 DurableMemoryStatus 类型 union 包含 'expired'
  const s: DurableMemoryStatus = "expired"
  expect(s).toBe("expired")
})
```

### 4.7 文档同步（3 文件 + 2 行）

- `butler-v5/DESIGN.md` §12 audit state 加 G1 行（"candidate expires cleanup 2026-09-XX D40 ship；status='expired' soft delete"）
- `butler-v5/DESIGN.md` §18 row 3 保留 "🟡 MVP ship + G3 batch UI" — 加 1 行 "G1 expires 已 ship（如实施）"
- `butler-v5/packages/ports/port-catalog.md` 不改（0 新 Core Port）

### 4.8 边界遵守

- §3 6 硬规则（D33 lock）：0 触（Core 不 import adapter / 不反向依赖 / Governance SDK-isolated）
- §20 16 invariant（D26A + D26B）：0 触
- §12 D30 6 cases + D39 G3 实证：保留 + 加 1 case
- §11.4 不默认建设：0 触（不建 broker / bus）
- §18 #11 不默认建设：0 触（同进程 timer）
- §13 风险与自治：0 触（sweep 不发外发 / 不调 LLM / 不写 grant）
- §14 observability：0 新 first-class event（logger 走现有 operator log）

---

## 5. 测试策略

### 5.1 Test cases（~17 cases 总）

| Suite | Cases | 范围 |
|-------|-------|------|
| `durable-memory-store.test.ts` (扩 6) | `listExpiredCandidates` 0/1/N/limit/不含 confirmed; `markExpired` 0/1/N/已 expired 不动/已 confirmed 不动 | persistence 层 |
| `candidate-expires.test.ts` (new, 5) | 7d 边界 (just over / just under) / 空 list / N 标 N / 部分 idempotent / 抛错 propagate | domain 纯函数 |
| `candidate-expires-sweeper.test.ts` (new, 6) | config env 解析 + default / off → null / on → tick / tick error → next tick / stop / runCandidateExpiresTick 直接调 | 调度层 |
| `tests/architecture/section12-knowledge-memory.test.ts` (扩 1) | `'expired'` 合法 status (G1 evidence) | arch guard |

### 5.2 Coverage target

- 新文件 `candidate-expires.ts` + `candidate-expires-sweeper.ts`: 100% branch coverage（pure + 调度逻辑简单）
- 扩 `durable-memory-store.ts`: 新方法 100% line + branch

### 5.3 Regression scope

- D30 §12 6 cases: 保留
- D39 G3 batch UI 实证 cases: 保留
- owner-routes 5 boundary tests: 保留（加 `'expired'` → 409 guard 是新 1 case，不动现有）

### 5.4 Test gates

- typecheck: 0 错
- lint: 0 错 0 警（plan 写明"每 commit 后跑 lint 闭环"）
- test (production): +18 cases (D39 1360 → D40 ~1378)
- test:archived: 101 pass（持平）
- arch guard: D30 §12 + D39 G3 + D40 G1 全通过

---

## 6. 文件 ops 清单（预估 ~7 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `packages/persistence/src/durable-memory-store.ts` | +50/-0 | 新增 2 方法 + JSDoc |
| `packages/persistence/src/durable-memory-store.test.ts` | +150/-0 | 6 cases |
| `packages/domain/src/knowledge/durable-memory.ts` | +3/-2 | enum 加 `'expired'` |
| `packages/domain/src/knowledge/durable-memory.test.ts` (if exists) | +20/-0 | enum case |
| `packages/domain/src/knowledge/candidate-expires.ts` (new) | +60/-0 | pure fn |
| `packages/domain/src/knowledge/candidate-expires.test.ts` (new) | +120/-0 | 5 cases |
| `apps/api/src/candidate-expires-sweeper.ts` (new) | +130/-0 | opt-in sweeper |
| `apps/api/src/candidate-expires-sweeper.test.ts` (new) | +200/-0 | 6 cases |
| `apps/api/src/server.ts` (or wiring.ts) | +3/-0 | 1 import + 1 调用 |
| `apps/api/src/owner-routes.ts` | +15/-0 | `status='expired'` 409 guard |
| `apps/api/src/owner-routes.test.ts` | +40/-0 | 1 new case |
| `tests/architecture/section12-knowledge-memory.test.ts` | +25/-0 | G1 evidence |
| `butler-v5/DESIGN.md` | +6/-0 | §12 + §18 audit state 扩 G1 行 |
| `docs/superpowers/specs/2026-09-01-durable-memory-candidate-expires-cleanup-design.md` (this) | +300/-0 | spec |
| `docs/superpowers/plans/2026-09-01-durable-memory-candidate-expires-cleanup.md` | +200/-0 | plan (plan 阶段产出) |

总预估: ~13 file ops / +1300 prod+test / +60 doc-only

---

## 7. 不做（明确范围外）

- **G2 dedup similar candidates**：与 §12 line 600 "无来源经验沉积" 重叠；需 similarity fn；本轮不动
- **G4 Layer 1→2 auto-promote**：违反 §12 line 599 "默认不建设 Dream 两阶段自动巩固"；明确不做
- **G5 跨 project PK recall**：动 `recall_project_knowledge` 工具语义（`tools.ts:478-479`）；本轮不动
- **G6 model-side `ingest_document` 工具**：与 §12 line 599 "默认不建设 自动全盘索引" 冲突；明确不做
- **独立 worker 进程**：违反 §18 #11 "单进程隔离实测不足才建"；同进程 timer 足够
- **新 Core Port (MaintenanceService 等)**：与 Channel Port 类比；待 §7 audit 触发；本轮不动
- **cron job 框架**：不引入 `node-cron` 等；纯 `setTimeout` 递归（同 schedule-worker 模式）
- **new first-class event**：沿用 logger；不扩 §14 边界
- **owner 主动 expire 接口**：sweeper 内部触发；owner 不会主动 expire（语义混乱）
- **auto-purge hard delete**：默认 soft delete 保留历史；如 owner 真要 hard delete 留待下轮

---

## 8. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-01-durable-memory-candidate-expires-cleanup.md`（plan 阶段产出）
2. **实施**: 扩 persistence + 新 candidate-expires.ts + 新 candidate-expires-sweeper.ts + server.ts 接入 + owner-routes 409 guard + DESIGN 同步 + arch guard 1 case
3. **验证**: typecheck + lint（每 commit 后跑）+ test (production) + test:archived + arch guard pass
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D40-section12-g1-expires-cleanup-2026-09-XX.md`（仿 D39 / D38 格式）
5. **commit**: `feat(arch): D40 §12 G1 candidate expires cleanup + 'expired' status`
6. **Handoff**: `.blackboard/shifts/2026-09-XX-d40-g1-expires-cleanup-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D41: G2 dedup + G5 跨 project recall（如 owner 真撞）
   - D42+: G4 auto-promote（仅当 owner 改变 §12 设计原则时）

---

## 9. 关联

- D30 §12 audit state（6 cases lock）— `memory/project-fix-D30-section12-knowledge-2026-08-31.md`
- D39 §12 G3 batch candidate UI — `memory/project-fix-D39-section12-batch-ui-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-batch-candidate-ui-design.md`
- §18 row 3 MVP ship + G3 — `DESIGN.md` §18 line 801
- §11.4 + §18 #11 不默认建设 — `DESIGN.md` §11.4 line 565-573 + §18 line 809
- §20 #11 schedule 不创建第二套 Loop — `DESIGN.md` §20 line 852
- §20 #12 没有真实触发证据不引入新进程 — `DESIGN.md` §20 line 853
- §3 6 硬规则（D33 lock）— `memory/project-fix-D33-section3-dependency-2026-08-31.md`
- D26A + D26B §20 16 invariant — `memory/project-fix-D26A-section20-batch-A-2026-08-31.md` + `memory/project-fix-D26B-section20-batch-B-2026-08-31.md`

---

**Spec version**: v1 (brainstorming closed 2026-09-01)
**Spec status**: awaiting user review
