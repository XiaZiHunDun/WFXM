# Durable Memory Auto-Promote — 设计 spec (G4)

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-01-durable-memory-auto-promote.md`（plan 阶段产出）。
> **背景**：D39 G3 batch UI + D40 G1 expires cleanup + D41 G2 dedup 已 ship。owner 撞的下一阶段痛点是"candidate 长期滞留要 owner 逐条 confirm"。G4 闭环 §12 知识层 4 治理链路 (G3 batch UI + G1 expiry + G2 dedup + **G4 auto-promote**)。本 spec 实施 G4 — candidate 创建 3d 内未 owner 操作的自动 promote 到 confirmed；owner 有 7d post-promote 撤销窗口 + rollback API + audit log 3 层 safety net。
> **优先级**：G4 auto-promote only；G5 跨 project PK recall 仍留待下轮。
> **影响面**：`packages/domain/src/knowledge/auto-promote.ts` 新文件（2 纯函数 + 4 interfaces）；`packages/persistence` 加 3 能力 (`findAutoPromoteCandidates` / `markAutoPromoted` / `rollbackAutoPromoted`) + 5 column migration + 1 partial index + Drizzle schema 同步；`apps/api/src/auto-promote-config.ts` 新文件 (env parser) + `apps/api/src/auto-promote-sweeper.ts` 新文件 (opt-in sweeper) + owner-routes 1 new route + DESIGN §12 audit state G4 行 + vitest config 扩 1 include。
> **预估 ops**：~19 file ops / ~+1900 prod+test lines / +500 doc-only lines / 10 commits (1 spec + 9 impl) / ~43 test cases

---

## 1. 目标

闭环 §12 知识层 4 治理链路 — G4 candidate auto-promote：

1. **Sweeper promote** — candidate 创建后 3d 自动 promote 到 status='confirmed'（同进程 opt-in sweeper，与 D40 G1 expiry sweeper 同模式）
2. **Owner 7d rollback window** — auto-promote 后 7d 内 owner 可一键 rollback 回 status='candidate' + 记录 audit log
3. **Pure domain + persistence pair** — `autoPromoteOldCandidates` + `rollbackAutoPromotedCandidate` 是 domain 纯函数；persistence 提供批量 promote + 单条 rollback
4. **§12 line 599 边界承认** — 违反 §12 line 599 "默认不建设" + §12 line 589 "模型生成默认 candidate 不是事实"；spec 显式承认，owner 3d rollback + 7d post-promote rollback window + audit log 提供 3 层 safety net
5. **§12 D30/D40/D41 lock 延伸** — 加 1 G4 arch guard case（regex-on-source 模式，D40/D41 实证 mirror）
6. **Schema 5 column + 1 partial index migration** — `promoted_by` / `promoted_at` / `rolled_back_by` / `rolled_back_at` / `rollback_reason`；§11 append-only 兼容
7. **0 first-class event 新增**：audit log 走现有 operator log 模式（与 G1 sweeper / G2 dedup 同模式）

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| 动机 | **(b) 架构补全** — G3 batch UI + G1 expiry + G2 dedup 已 ship；G4 闭环 §12 知识层 4 治理链路 |
| Trigger scope | **(A) 全部 candidate** — model 从 message 提取的 candidate 也 auto-promote；明确违反 §12 line 589 |
| Override | **(i) 有撤销窗口** — auto-promote 后 7d 内 owner 可 rollback；7d 后 confirmed 真"硬"committed |
| 执行模型 | **(a) sweeper pattern** — 与 G1 expiry sweeper 同模式；同进程 opt-in；6h interval |
| Promote window (T1) | **3d** — candidate age > 3d 自动 promote |
| Rollback window (T2) | **7d** — promote 后 7d 内 owner 可 rollback；与 G1 expiry window 对称 |
| Rollback API surface | **(β) 新 POST `/v1/owner/memories/:id/rollback-auto-promote`** — 语义清晰：rollback ≠ reject |
| Schema 5 column + 1 partial index | **5 column ADD + 1 partial index** — `promoted_by` / `promoted_at` / `rolled_back_by` / `rolled_back_at` / `rollback_reason`；`durable_memories_auto_promote_sweep_idx` partial WHERE status='candidate' |
| Race 与并发 safety | **WHERE status='candidate' / promoted_by='sweeper' 条件** — markAutoPromoted 不会重复 promote；rollbackAutoPromoted 不会 rollback owner-confirmed |
| §12 边界 | **违反 §12 line 599 默认不建设 + §12 line 589** — spec 显式承认；safety net 3 层 (rollback window + audit log + rollback API) |
| §18 关系 | **不进 §18 row 3** — G4 是 §12 知识层 4 治理链路 closure，非 trigger-conditioned |
| First-class event | **0 新增**；audit log 走 stderr + operator log（与 G1/G2 同模式）|
| Arch guard | D30 §12 suite 扩 1 Case10：`auto-promote.ts` exists + `autoPromoteOldCandidates` + `rollbackAutoPromotedCandidate` exported (regex-on-source mirror Case 9) |
| Embed-free | **保持** — 0 embedding column；与 D30 case #6 lock + §12 line 593 lock 一致 |
| 推下轮 | **G5 跨 project PK recall**（不动 `recall_project_knowledge` 工具语义）|

---

## 3. 现状与不一致

### 3.1 已 ship（D41 G2 闭环后）

- D30 §12 9 cases lock (D30 6 + D39 G3 + D40 G1 + D41 G2)
- D39 G3 batch candidate UI：3 owner routes (GET list + POST confirm-batch + POST reject-batch) + wechat `/记忆候选` + `/确认记忆` 扩面
- D40 G1 candidate expires cleanup：sweeper opt-in + owner-routes 409 guard + GET filter accepts expired
- D41 G2 candidate dedup：trigram Jaccard 0.85 阈值 + 409 + force=true bypass + wechat warning + audit log
- §12 line 593 + D30 case #6 lock：embedding 默认不启用
- §20 16 invariant lock + §3 6 硬规则 (D33) + §11 5 子段 audit 收口

### 3.2 真缺（1 gap）

- **Candidate 长期滞留 + owner 需逐条 confirm 累积**：candidate 创建后无 owner 操作则长期 status='candidate'；D40 G1 7d 后 expired，但 owner 没机会 promote 的就丢了；G4 auto-promote 解决"owner 不主动操作但 candidate 实际有效"场景

### 3.3 文档 drift

- DESIGN §12 audit state "留待下轮：G4 Layer 1→2 auto-promote" — 本 spec 实施后移除
- DESIGN §18 row 3 — G4 不进（保留 🟡 MVP ship + G3 + G1 + G2 状态）
- §12 line 597 "Dream 两阶段自动巩固" 默认不建设 — G4 明确违反，spec 显式承认

### 3.4 Persistence 缺口

- `DurableMemoryStore` 无 `findAutoPromoteCandidates` / `markAutoPromoted` / `rollbackAutoPromoted` 方法
- `durable_memories` 表无 `promoted_by` / `promoted_at` / `rolled_back_by` / `rolled_back_at` / `rollback_reason` column
- `durable_memories_auto_promote_sweep_idx` partial index 不存在
- 不改 `findCandidatesForDedup` / `listBySubject` / `countBySubject` / `listExpiredCandidates` / `markExpired` 现有方法

---

## 4. 设计

### 4.1 Domain pure fn（1 文件 + 2 test）

`butler-v5/packages/domain/src/knowledge/auto-promote.ts`（新文件）：

```typescript
/**
 * G4: candidate auto-promote (§12).
 * Pure function — caller owns store + window.
 */
export interface CandidateForPromote {
  readonly id: string
  readonly subject: string
  readonly content: string
  readonly createdAt: Date
}

export interface AutoPromoteOldCandidatesInput {
  readonly candidates: readonly CandidateForPromote[]
  readonly now: Date
  readonly windowMs: number // candidate age >= windowMs 才 promote
}

export interface AutoPromoteOldCandidatesResult {
  readonly toPromote: readonly CandidateForPromote[]
}

export function autoPromoteOldCandidates(
  input: AutoPromoteOldCandidatesInput,
): AutoPromoteOldCandidatesResult {
  const cutoff = input.now.getTime() - input.windowMs
  const toPromote = input.candidates.filter((c) => c.createdAt.getTime() < cutoff)
  return { toPromote }
}

/**
 * G4: rollback auto-promoted candidate.
 * Validates status='confirmed' AND promoted_by='sweeper' AND within rollback window.
 */
export interface RollbackAutoPromotedCandidateInput {
  readonly memory: {
    readonly id: string
    readonly status: 'confirmed'
    readonly promotedBy: 'sweeper'
    readonly promotedAt: Date
  }
  readonly ownerId: string
  readonly reason: string | undefined
  readonly now: Date
  readonly rollbackWindowMs: number // default 7d
}

export type RollbackAutoPromotedCandidateResult =
  | { readonly ok: true; readonly updated: UpdatedMemory }
  | { readonly ok: false; readonly reason: 'not-confirmed' | 'not-auto-promoted' | 'rollback-window-expired' }

export interface UpdatedMemory {
  readonly id: string
  readonly status: 'candidate'
  readonly updatedAt: Date
  readonly rolledBackBy: string
  readonly rolledBackAt: Date
  readonly rollbackReason: string | undefined
}

export function rollbackAutoPromotedCandidate(
  input: RollbackAutoPromotedCandidateInput,
): RollbackAutoPromotedCandidateResult {
  if (input.memory.status !== 'confirmed') {
    return { ok: false, reason: 'not-confirmed' }
  }
  if (input.memory.promotedBy !== 'sweeper') {
    return { ok: false, reason: 'not-auto-promoted' }
  }
  const rollbackDeadline = input.memory.promotedAt.getTime() + input.rollbackWindowMs
  if (input.now.getTime() > rollbackDeadline) {
    return { ok: false, reason: 'rollback-window-expired' }
  }
  return {
    ok: true,
    updated: {
      id: input.memory.id,
      status: 'candidate',
      updatedAt: input.now,
      rolledBackBy: input.ownerId,
      rolledBackAt: input.now,
      rollbackReason: input.reason,
    },
  }
}
```

**架构不变量遵守**：
- §20 #2: 接受 store 参数（依赖倒置），不 import 具体 adapter
- §20 #3: 副作用仅 DB + 内存计算（不是 LLM / 外发）
- §3 #4: Governance SDK-isolated — 不调 policy / grant / approver
- §20 #11: sweeper 是 Schedule.RunTrigger 边界；G4 sweep 复用 G1 expiry sweeper 同模式 (同进程 opt-in)

**测试**（`auto-promote.test.ts` + `auto-promote-rollback.test.ts` 新增 ~11 cases）：
- `autoPromoteOldCandidates` 5 cases: empty / 部分过期 / 全过期 / 边界 age = window / 多 subject
- `rollbackAutoPromotedCandidate` 6 cases: ok / not-confirmed / not-auto-promoted / window expired / no reason / with reason

### 4.2 Persistence 扩展（1 文件 + 1 migration）

`packages/persistence/src/durable-memory-store.ts`（+3 方法）：

```typescript
findAutoPromoteCandidates(input: {
  readonly now: Date
  readonly windowMs: number
  readonly limit: number
}): Promise<readonly CandidateForPromote[]>

markAutoPromoted(input: {
  readonly ids: readonly string[]
  readonly now: Date
}): Promise<number> // 返回实际 update count (含 WHERE status='candidate' 条件)

rollbackAutoPromoted(input: {
  readonly id: string
  readonly ownerId: string
  readonly reason: string | undefined
  readonly now: Date
}): Promise<UpdatedMemory | null>
```

**SQL 等价**：

```sql
-- findAutoPromoteCandidates
SELECT id, subject, content, created_at FROM durable_memories
WHERE status = 'candidate'
  AND created_at < $1  -- now - windowMs
ORDER BY created_at ASC
LIMIT $2;

-- markAutoPromoted
UPDATE durable_memories
SET status = 'confirmed',
    updated_at = $2,
    promoted_by = 'sweeper',
    promoted_at = $2
WHERE id = ANY($1) AND status = 'candidate';

-- rollbackAutoPromoted
UPDATE durable_memories
SET status = 'candidate',
    updated_at = $4,
    rolled_back_by = $2,
    rolled_back_at = $4,
    rollback_reason = $3
WHERE id = $1
  AND status = 'confirmed'
  AND promoted_by = 'sweeper'
RETURNING id, status, updated_at, rolled_back_by, rolled_back_at, rollback_reason;
```

**Migration** (`packages/persistence/migrations/00XX_add_auto_promote_columns.sql` 新):

```sql
ALTER TABLE durable_memories
  ADD COLUMN promoted_by TEXT,           -- 'owner' | 'sweeper' | NULL
  ADD COLUMN promoted_at TIMESTAMPTZ,    -- sweeper promote time, NULL for owner-confirmed
  ADD COLUMN rolled_back_by TEXT,        -- owner who rolled back (NULL if never)
  ADD COLUMN rolled_back_at TIMESTAMPTZ,
  ADD COLUMN rollback_reason TEXT;

CREATE INDEX durable_memories_auto_promote_sweep_idx
  ON durable_memories (created_at)
  WHERE status = 'candidate';
```

§11 append-only 兼容：5 column ADD（不删/不改现有 column）+ 1 partial index。

**测试**（`durable-memory-store.test.ts` 新增 ~12 cases）：
- `findAutoPromoteCandidates` 4 cases: 0 candidate / 部分过期 / limit boundary / status filter
- `markAutoPromoted` 4 cases: N candidates all promoted / 部分已 promote (WHERE 条件跳过) / 0 candidate / 并发安全
- `rollbackAutoPromoted` 5 cases: ok / not-confirmed (status filter) / not-sweeper (promoted_by filter) / window expired / 并发安全

### 4.3 API 配置（1 文件 + 1 test）

`butler-v5/apps/api/src/auto-promote-config.ts`（新文件）：

```typescript
export interface AutoPromoteConfig {
  readonly enabled: boolean         // env flag opt-in
  readonly windowMs: number         // default 3d
  readonly sweepLimit: number       // default 500
  readonly sweepIntervalHours: number // default 6
  readonly rollbackWindowMs: number // default 7d
}

export function parseAutoPromoteConfig(env: NodeJS.ProcessEnv): AutoPromoteConfig {
  return {
    enabled: env["BUTLER_V5_AUTO_PROMOTE_ENABLED"] === "1",
    windowMs: parseIntSafe(env["BUTLER_V5_AUTO_PROMOTE_WINDOW_DAYS"], 3) * 24 * 3_600_000,
    sweepLimit: parseIntSafe(env["BUTLER_V5_AUTO_PROMOTE_SWEEP_LIMIT"], 500),
    sweepIntervalHours: parseIntSafe(env["BUTLER_V5_AUTO_PROMOTE_SWEEP_INTERVAL_HOURS"], 6),
    rollbackWindowMs: parseIntSafe(env["BUTLER_V5_AUTO_PROMOTE_ROLLBACK_WINDOW_DAYS"], 7) * 24 * 3_600_000,
  }
}
```

### 4.4 Sweeper（1 文件 + 1 test）

`butler-v5/apps/api/src/auto-promote-sweeper.ts`（新文件, ~80 行）：

```typescript
import { autoPromoteOldCandidates } from "@butler/domain/knowledge/auto-promote.js"
import { parseAutoPromoteConfig } from "./auto-promote-config.js"

export interface AutoPromoteSweeperDeps {
  readonly store: DurableMemoryStore
  readonly now: () => Date  // injected for test
}

export class AutoPromoteSweeper {
  private readonly deps: AutoPromoteSweeperDeps
  private readonly cfg: AutoPromoteConfig
  private intervalHandle: NodeJS.Timeout | null = null

  constructor(deps: AutoPromoteSweeperDeps, cfg: AutoPromoteConfig) {
    this.deps = deps
    this.cfg = cfg
  }

  async runOnce(): Promise<{ promoted: number }> {
    const now = this.deps.now()
    const candidates = await this.deps.store.findAutoPromoteCandidates({
      now,
      windowMs: this.cfg.windowMs,
      limit: this.cfg.sweepLimit,
    })
    const { toPromote } = autoPromoteOldCandidates({ candidates, now, windowMs: this.cfg.windowMs })
    if (toPromote.length === 0) return { promoted: 0 }
    const count = await this.deps.store.markAutoPromoted({
      ids: toPromote.map((c) => c.id),
      now,
    })
    console.error(`[memory-auto-promote] promoted ${count} ids window=${this.cfg.windowMs}ms`)
    return { promoted: count }
  }

  start(): void {
    if (!this.cfg.enabled) return
    const intervalMs = this.cfg.sweepIntervalHours * 3_600_000
    this.intervalHandle = setInterval(() => {
      this.runOnce().catch((err) => {
        console.error("[memory-auto-promote] sweeper error:", err instanceof Error ? err.message : String(err))
      })
    }, intervalMs)
  }

  stop(): void {
    if (this.intervalHandle !== null) {
      clearInterval(this.intervalHandle)
      this.intervalHandle = null
    }
  }
}
```

**Pattern**: 与 D40 G1 `candidate-expires-sweeper.ts` 镜像（同进程 opt-in setInterval；fail-batch not fail-all）。

### 4.5 调用点更新（1 route）

`butler-v5/apps/api/src/owner-routes.ts`（+1 route）：

```typescript
app.post('/v1/owner/memories/:id/rollback-auto-promote', async (req, res) => {
  const { id } = req.params
  const { reason } = req.body ?? {}
  const ownerId = req.auth.ownerId  // 现有 owner auth 中间件
  const now = new Date()

  const memory = await store.get(id)
  if (memory === null) {
    return res.status(404).json({ error: 'not-found' })
  }

  const result = rollbackAutoPromotedCandidate({
    memory: {
      id: memory.id,
      status: memory.status,
      promotedBy: memory.promotedBy,
      promotedAt: memory.promotedAt,
    },
    ownerId,
    reason,
    now,
    rollbackWindowMs: cfg.rollbackWindowMs,
  })

  if (!result.ok) {
    return res.status(409).json({
      error: result.reason,
      currentStatus: memory.status,
      promotedBy: memory.promotedBy,
      promotedAt: memory.promotedAt,
      rollbackDeadline: memory.promotedAt
        ? new Date(memory.promotedAt.getTime() + cfg.rollbackWindowMs).toISOString()
        : null,
    })
  }

  const updated = await store.rollbackAutoPromoted({
    id,
    ownerId,
    reason,
    now,
  })
  if (updated === null) {
    // 并发 race: between validation and UPDATE, status/promoted_by changed
    return res.status(409).json({ error: 'concurrent-modification' })
  }

  console.error(`[memory-rollback] owner=${ownerId} id=${id} reason=${reason ?? 'none'}`)
  return res.status(200).json({ memory: updated })
})
```

**1 site 集成**：`owner-routes.ts` 新增 route。wechat 不暴露 rollback（wechat 是低信任通道，rollback 应走 owner 显式 UI）。

### 4.6 测试策略（~43 cases）

| Suite | Cases |
|-------|-------|
| `auto-promote.test.ts` (new, 5) | `autoPromoteOldCandidates` 5 cases (empty / 部分 / 全 / 边界 / 多 subject) |
| `auto-promote-rollback.test.ts` (new, 6) | `rollbackAutoPromotedCandidate` 6 cases (ok / not-confirmed / not-sweeper / window expired / no reason / with reason) |
| `durable-memory-store.test.ts` (扩 12) | 3 新方法 12 cases (含并发 + WHERE 条件) |
| `auto-promote-config.test.ts` (new, 4) | default / env override / disabled (enabled=0) / 全部 env |
| `auto-promote-sweeper.test.ts` (new, 6) | empty / 部分 promote / DB error skip / markAutoPromoted 抛错 / 与 G1 expiry 顺序保证 / 多 cycle idempotent |
| `owner-routes.test.ts` (扩 5) | POST `/rollback-auto-promote` 5 cases (ok / 404 / 409 not-confirmed / 409 not-sweeper / 409 window expired) |
| `auto-promote-rollback-race.test.ts` (new, 4) | 并发 rollback + markPromoted / 并发 rollback + G1 expiry / 并发 rollback + 新 candidate 创建 / 并发 rollback 多次 |
| `tests/architecture/section12-knowledge-memory.test.ts` (扩 1) | §12 G4 Case10: `auto-promote.ts` exists + `autoPromoteOldCandidates` exported (regex-on-source mirror Case 9) |

### 4.7 边界遵守（DESIGN §段）

- §3 6 硬规则 (D33 lock): 0 触 (Core 接受 store 参数依赖倒置；不 import adapter)
- §20 16 invariant (D26A + D26B): 0 触
- §12 D30/D40/D41: 保留 + 加 1 G4 case
- §12 line 599 "默认不建设 Dream 两阶段自动巩固" + §12 line 589 "模型生成默认 candidate 不是事实": **G4 明确违反承认**; 3 层 safety net (3d promote + 7d rollback window + audit log + rollback API)
- §12 line 593 "默认先用结构化字段" + D30 case #6 lock "默认不启用 embedding": 0 触
- §13 风险与自治: 0 触 (rollback 409 路径明确; 0 grant/approver/policy)
- §14 observability: 0 新 first-class event; audit log 走 stderr + operator log
- §11 append-only: 5 column ADD + 1 partial index; 不删/不改现有 column
- §11.4 / §18 #11 不默认建设: 0 触 (同进程 sweeper 复用 G1 pattern; 不建 broker / 独立 worker)
- §7.1 port snapshot: 0 新 Core Port (复用 DurableMemoryStore)
- §18 row 3: 保留 🟡 MVP ship + G3 + G1 + G2 状态; G4 不进 §18 row 3

### 4.8 数据流与 race 边界

**Happy path**:

```
candidate created (day 0, status=candidate)
     ↓ wait 3d
G4 sweeper run (6h interval, day 3~3.25)
     ↓ findAutoPromoteCandidates({windowMs: 3d})
     ↓ autoPromoteOldCandidates (domain pure) → [candidate_x, candidate_y, ...]
     ↓ markAutoPromoted (UPDATE status='confirmed', promoted_by='sweeper', promoted_at=now)
     ↓ audit log: [memory-auto-promote] promoted 3 ids window=259200000ms
     ↓ status=confirmed for N candidates
     ↓
owner 看到 auto-promoted list (走现有 GET /v1/owner/memories?status=confirmed)
     ↓
[可选] owner 决定 rollback:
     ↓
POST /v1/owner/memories/:id/rollback-auto-promote {reason}
     ↓ rollbackAutoPromotedCandidate (domain pure) validate
     ↓   - status === 'confirmed'?
     ↓   - promoted_by === 'sweeper'?
     ↓   - now < promoted_at + 7d?
     ↓ rollbackAutoPromoted (DB UPDATE WHERE status='confirmed' AND promoted_by='sweeper')
     ↓ audit log: [memory-rollback] owner=X id=Y reason=Z
     ↓ status=candidate again (rolled_back_at = now)
     ↓ 下一个 sweep cycle (3d 后): 又 promote (unless owner reject)
```

**与 G1 expiry sweeper race 关系**:

```
candidate day 0
     ↓
day 3-3.25: G4 sweep → status=confirmed
day 6h interval: 重复 G4 sweep (idempotent: WHERE status='candidate' 跳过)
day 7-7.25: G1 expiry sweep (window=7d, lookback=day0)
     → IF status=confirmed: 跳过 (G1 只看 status=candidate)
     → IF status=candidate (rolled back): 标记 expired
day 14: G1 重复 sweep (idempotent: status != candidate 跳过)

关键: G4 promote (3d) 先于 G1 expiry (7d) → 无 race, 不会 promote expired
```

**并发 safety**:

| Operation | WHERE clause | 防止 |
|-----------|--------------|------|
| `markAutoPromoted` | `id = ANY(${ids}) AND status='candidate'` | 双重 promote (owner 与 sweeper race) |
| `rollbackAutoPromoted` | `id=? AND status='confirmed' AND promoted_by='sweeper'` | owner-confirmed 被误 rollback |
| G1 expiry sweep | `status='candidate'` | confirmed 被误 expire |
| rollback API 并发 | domain validate + DB UPDATE 两阶段 | validate 与 UPDATE 间 status 变化 (返回 409 concurrent-modification) |

**Error handling**:

| 失败点 | 处理 |
|--------|------|
| Sweeper `findAutoPromoteCandidates` 抛错 | log + skip batch (整个 run 不崩); 下一 cycle retry |
| `markAutoPromoted` 抛错 (DB conn lost) | log + skip; WHERE status='candidate' 条件保证 idempotent retry |
| Sweeper race (2 实例同时跑) | WHERE status='candidate' 条件 + advisory lock 或进程单例 (D40 G1 sweeper 用 opt-in 隐式单实例) |
| rollback API: not-found (id 不存在) | 404 Not Found |
| rollback API: not-confirmed (status != 'confirmed') | 409 Conflict `{ error: 'not-confirmed', currentStatus: ... }` |
| rollback API: not-sweeper-promoted (promoted_by != 'sweeper') | 409 Conflict `{ error: 'not-auto-promoted', promotedBy: 'owner' }` |
| rollback API: rollback window 过期 (promoted_at + 7d < now) | 409 Conflict `{ error: 'rollback-window-expired', promotedAt: ..., rollbackDeadline: ... }` |
| rollback API: 并发修改 (validate 后 UPDATE 前 status 变化) | 409 Conflict `{ error: 'concurrent-modification' }` |
| rollback API DB error | log + 500 Internal (与现有 owner-routes error 模式一致) |
| Sweeper 与 G1 expiry race | 不可达 (G4 promote 先于 G1 expiry); 即使偶发 G4 mark 一个 G1 刚 expire 的 candidate, G4 WHERE status='candidate' 条件自然跳过 |

---

## 5. 文件 ops 清单（预估 ~14 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `packages/domain/src/knowledge/auto-promote.ts` (new) | +85/-0 | 2 pure fn + 4 interfaces |
| `packages/domain/src/knowledge/auto-promote.test.ts` (new) | +90/-0 | 5 cases |
| `packages/domain/src/knowledge/auto-promote-rollback.test.ts` (new) | +120/-0 | 6 cases |
| `packages/persistence/src/durable-memory-store.ts` | +60/-0 | 3 新方法 |
| `packages/persistence/src/durable-memory-store.test.ts` | +150/-0 | 12 新 cases |
| `packages/persistence/migrations/00XX_add_auto_promote_columns.sql` (new) | +20/-0 | 5 column + 1 partial index |
| `packages/persistence/src/schema.ts` (Drizzle) | +30/-0 | schema 同步 |
| `apps/api/src/auto-promote-config.ts` (new) | +35/-0 | env parser |
| `apps/api/src/auto-promote-config.test.ts` (new) | +50/-0 | 4 cases |
| `apps/api/src/auto-promote-sweeper.ts` (new) | +90/-0 | opt-in sweeper |
| `apps/api/src/auto-promote-sweeper.test.ts` (new) | +120/-0 | 6 cases |
| `apps/api/src/auto-promote-rollback-race.test.ts` (new) | +80/-0 | 4 race cases |
| `apps/api/src/owner-routes.ts` | +60/-0 | 1 new route + rollback helper |
| `apps/api/src/owner-routes.test.ts` | +90/-0 | 5 new cases |
| `tests/architecture/section12-knowledge-memory.test.ts` | +30/-0 | G4 Case10 |
| `butler-v5/vitest.config.ts` | +4/-0 | include new tests |
| `butler-v5/DESIGN.md` | +6/-3 | §12 G4 audit state + 移除 "留待下轮 G4" |
| `docs/superpowers/specs/2026-09-01-durable-memory-auto-promote-design.md` (this) | +500/-0 | spec |
| `docs/superpowers/plans/2026-09-01-durable-memory-auto-promote.md` | +350/-0 | plan (plan 阶段产出) |

总预估: ~19 file ops / +1900 prod+test / +500 doc-only

---

## 6. 不做（明确范围外）

- **G5 跨 project PK recall**: 动 `recall_project_knowledge` 工具语义；本轮不动
- **embedding-based auto-promote**: 违反 D30 case #6 lock + §12 line 593；明确不做
- **Owner-confirmed memory rollback**: rollback API 仅作用于 `promoted_by='sweeper'`；owner 自己 confirm 的不能 rollback（破坏 confirmed 语义）
- **Auto-merge similar candidates during promote**: 复杂度过高；本轮 1:1 promote，不 merge
- **Bounce prevention (rollback 后 N 次自动 reject)**: 复杂度爆炸；本轮接受"owner 可 rollback 多次"语义；owner 拒后悔走 rejectDurableMemory
- **主动 notification (auto-promote 后推送 owner)**: 动 §14 observability；本轮 audit log + GET list 足够
- **Per-record timer (instead of sweeper)**: scope 创 new；本轮 sweeper pattern
- **New Core Port (MemoryAutoPromote 等)**: 复用 DurableMemoryStore；与 §7 audit 一致
- **Cron / schedule cleanup of sweeper leftovers**: sweeper 自身 idempotent；本轮不动
- **Cross-subject auto-promote**: 复杂度爆炸；本轮仅同 subject 内 promote
- **Auto-promote confidence threshold (按 confidence 字段分级 promote)**: §12 line 589 不区分；本轮 A 全部

---

## 7. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-01-durable-memory-auto-promote.md`（plan 阶段产出）
2. **实施**: 9 tasks (T1 migration + T2/T3 domain + T4/T5 persistence + T6 sweeper + T7 owner-routes + T8 arch guard + T9 DESIGN sync)
3. **验证**: typecheck + lint（每 commit 后跑）+ test (production) + test:archived + arch guard pass (10/10 cases)
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D42-section12-g4-auto-promote-2026-09-01.md`（仿 D40/D41 格式）
5. **commit**: 10 commits (1 spec + 9 impl) with conventional commit format
6. **Handoff**: `.blackboard/shifts/2026-09-01-d42-g4-auto-promote-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D43: G5 跨 project PK recall（如 owner 真撞）
   - D44+: 工程治理 (pre-commit hook line 113 silent-exit / dead code / refactor-clean)

---

## 8. 关联

- D30 §12 audit state (9 cases lock) — `memory/project-fix-D30-section12-knowledge-2026-08-31.md`
- D39 §12 G3 batch UI — `memory/project-fix-D39-section12-batch-ui-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-batch-candidate-ui-design.md`
- D40 §12 G1 candidate expires cleanup — `memory/project-fix-D40-section12-g1-expires-cleanup-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-candidate-expires-cleanup-design.md`
- D41 §12 G2 candidate dedup — `memory/project-fix-D41-section12-g2-dedup-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-dedup-design.md`
- §12 line 589/593/599/600 — `DESIGN.md` §12 主规则
- §18 row 3 — `DESIGN.md` line 803（保留 🟡 MVP ship + G3 + G1 + G2 状态；G4 不进 §18）
- §3 6 硬规则 (D33 lock) — `memory/project-fix-D33-section3-dependency-2026-08-31.md`
- §11 append-only + §11.2 migration — `memory/project-fix-D28-section11-1-2-3-2026-08-31.md`
- §20 16 invariant (D26A + D26B) — `memory/project-fix-D26A-section20-batch-A-2026-08-31.md` + `memory/project-fix-D26B-section20-batch-B-2026-08-31.md`
- ExpireCandidatesStore pattern (D40 T3 implementer 创造) — `packages/domain/src/knowledge/candidate-expires.ts:8-16`
- DedupStore pattern (D41 T2 fix c5791623) — `packages/domain/src/knowledge/dedup.ts:6-15`
- candidate-expires-sweeper pattern (D40 G1 sweeper) — `apps/api/src/candidate-expires-sweeper.ts`
- RuntimeStore pattern reference — `packages/domain/src/runtime/store-contract.ts:61-210`

---

**Spec version**: v1 (brainstorming closed 2026-09-01)
**Spec status**: awaiting user review