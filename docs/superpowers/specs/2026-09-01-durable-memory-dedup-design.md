# Durable Memory Dedup — 设计 spec (G2)

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-01-durable-memory-dedup.md`（plan 阶段产出）。
> **背景**：D39 G3 batch UI + D40 G1 expires cleanup 已 ship。owner 撞的下一个痛点是重复 candidate 堆积 — D40 expires 清理了 stale，但新 candidate 仍可能与已有记忆（confirmed / pending / rejected）近重复。本 spec 实施 G2 dedup — 在 candidate 创建时通过 trigram Jaccard 检测与已存在记忆的相似度，超过阈值返回 409 with existingMemoryId（owner 可 `force=true` bypass）。
> **优先级**：G2 dedup only；其余 G4 Layer 1→2 auto-promote / G5 跨 project PK recall 留待下轮。
> **影响面**：`packages/domain/src/knowledge/dedup.ts` 新文件（pure fn）；`packages/persistence` 加 `findCandidatesForDedup` 1 能力；`apps/api/src/dedup-config.ts` 新文件（env parser）；3 call sites 加 dedup check（owner-routes 2 处 + wechat 1 处）；D30 §12 arch guard 加 1 case。

---

## 1. 目标

解决 owner 撞的下一阶段痛点 — duplicate candidate 堆积：

1. **Block candidate creation** — 创建时检测 trigram Jaccard ≥ 0.85 vs 已存在记忆（confirmed + candidate + rejected，expired 不算），返回 409 with existingMemoryId
2. **Pure domain + persistence pair** — 核心 trigram Jaccard + findSimilarMemories 是 domain 纯函数；persistence 只提供候选拉取
3. **Owner bypass** — body 加 `force=true` 显式绕过；logger.info 记录 "forced dup" for audit
4. **Embed-free** — 不用 embedding（D30 case #6 lock + §12 line 593 lock 保持）；trigram 是字符 n-gram 结构化方法
5. **§12 D30 lock 延伸** — 加 1 G2 arch guard case（regex-on-source 模式，D40 G1 实证的 mirror）
6. **0 first-class event 新增**：logger 走现有 operator log（与 schedule-worker / candidate-expires-sweeper 同模式）

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| 语义 | **Block 创建**（vs Surface in listing / Auto-reject / Hybrid） |
| Similarity 函数 | **Trigram Jaccard**（vs Levenshtein / Hybrid trigram+sourceKind） |
| 比对范围 | **All**（confirmed + candidate + rejected；expired 不算） |
| Threshold | **Single 0.85**，env `BUTLER_V5_MEMORY_DEDUP_THRESHOLD`（0 = off，opt-out） |
| 返回 | **409 with existingMemoryId + similarity** |
| Override | body `force=true` bypass + logger.info audit |
| 失败处理 | dedup DB 错误不阻止 owner 写（fail-open，§20 #11 守住 owner 自主权） |
| Schema | 0 变化（`content` 已存在，纯函数计算） |
| First-class event | 0 新增；logger 走现有 operator log |
| Arch guard | D30 §12 suite 扩 1 case：`dedup.ts` exists + `trigramJaccard` exported |
| 推下轮 | G4 Layer 1→2 auto-promote / G5 跨 project PK recall |

---

## 3. 现状与不一致

### 3.1 已 ship（D40 闭环后）

- D30 §12 D40 4-member union (`candidate` / `confirmed` / `rejected` / `expired`) + 8 arch guard cases lock
- D39 G3 batch candidate UI：3 owner routes（GET list + POST confirm-batch + POST reject-batch）+ wechat `/记忆候选` + `/确认记忆` 扩面
- D40 G1 candidate expires cleanup：sweeper opt-in + owner-routes 409 guard + GET filter accepts expired
- `DurableMemoryStore` 已含：`create` / `get` / `update` / `delete` / `listBySubject` / `countBySubject` / `listExpiredCandidates` / `markExpired` / `deleteBySourceMessageId` / `deleteBySourceDocumentId`
- §12 line 593 + D30 case #6 lock：embedding 默认不启用

### 3.2 真缺（1 gap）

- **重复 candidate 创建无拦截**：owner 显式 POST candidate 或 wechat `/记住` 创建 candidate 时，不检查是否与已存在记忆（confirmed + candidate + rejected）近重复；duplicate candidate 堆积无解

### 3.3 文档 drift

- 无 doc drift；本 spec 实施后 §12 audit state 加 G2 行；§18 row 3 状态保留 🟡 MVP ship + G3 + G1（G2 不进 §18 — G2 是 §12 line 600 边界内的功能扩展，非 trigger-conditioned）

### 3.4 Persistence 缺口

- `DurableMemoryStore` 无 `findCandidatesForDedup` 方法
- 不改 `listBySubject` / `countBySubject` / `listExpiredCandidates` / `markExpired` 现有方法

---

## 4. 设计

### 4.1 Domain pure fn（1 文件 + 1 test）

`butler-v5/packages/domain/src/knowledge/dedup.ts`（新文件）：

```typescript
/**
 * G2: candidate dedup via trigram Jaccard (§12).
 * Pure function — caller owns store + threshold + status filter.
 */
import type { ExpireCandidatesStore } from "./candidate-expires.js" // 复用 G1 的 minimal store contract 模式

/** Minimal store contract — persistence's DurableMemoryStore satisfies via structural typing. */
export interface DedupStore extends ExpireCandidatesStore {
  readonly findCandidatesForDedup: (input: {
    readonly subject: string
    readonly statuses: readonly DurableMemoryStatus[]
    readonly recentMs: number // 限定窗口期，避免全表扫历史
    readonly limit: number
  }) => Promise<readonly { id: string; content: string; status: DurableMemoryStatus }[]>
}

import type { DurableMemoryStatus } from "./durable-memory.js"

export interface FindSimilarMemoriesInput {
  readonly store: DedupStore
  readonly subject: string
  readonly content: string
  readonly threshold: number      // 0..1；>= threshold 视为重复
  readonly statuses: readonly DurableMemoryStatus[]
  readonly recentMs?: number      // default 90d
  readonly limit?: number         // default 50
}

export interface SimilarMemoryMatch {
  readonly id: string
  readonly content: string
  readonly status: DurableMemoryStatus
  readonly similarity: number
}

export interface FindSimilarMemoriesResult {
  readonly best: SimilarMemoryMatch | null
  readonly scanned: number
}

/** Trigram (3-char window) Jaccard similarity. Returns 0..1. */
export function trigramJaccard(a: string, b: string): number {
  const aGrams = trigrams(a)
  const bGrams = trigrams(b)
  if (aGrams.size === 0 && bGrams.size === 0) return 1.0
  let intersect = 0
  for (const g of aGrams) if (bGrams.has(g)) intersect++
  const union = aGrams.size + bGrams.size - intersect
  return union === 0 ? 0 : intersect / union
}

function trigrams(s: string): Set<string> {
  const padded = `  ${s.trim().toLowerCase()}  `
  const grams = new Set<string>()
  for (let i = 0; i < padded.length - 2; i++) {
    grams.add(padded.slice(i, i + 3))
  }
  return grams
}

export async function findSimilarMemories(
  input: FindSimilarMemoriesInput,
): Promise<FindSimilarMemoriesResult> {
  const recentMs = input.recentMs ?? 90 * 24 * 3_600_000
  const limit = input.limit ?? 50
  const candidates = await input.store.findCandidatesForDedup({
    subject: input.subject,
    statuses: input.statuses,
    recentMs,
    limit,
  })
  let best: SimilarMemoryMatch | null = null
  for (const c of candidates) {
    const similarity = trigramJaccard(input.content, c.content)
    if (similarity >= input.threshold && (best === null || similarity > best.similarity)) {
      best = { id: c.id, content: c.content, status: c.status, similarity }
    }
  }
  return { best, scanned: candidates.length }
}
```

**架构不变量遵守**：
- §20 #2: 接受 store 参数（依赖倒置），不 import 具体 adapter
- §20 #3: 副作用仅 DB + 内存计算（不是 LLM / 外发）
- §3 #4: Governance SDK-isolated — 不调 policy / grant / approver
- §20 #11: 不是 Schedule.RunTrigger；不创建 Loop

**测试**（`dedup.test.ts` 新增 ~8 cases）：
- `trigramJaccard` 4 cases (identical / empty / partial / reorder)
- `findSimilarMemories` 4 cases (0 match / 1 match above threshold / threshold edge case / limit boundary)

### 4.2 Persistence 扩展（1 文件）

`butler-v5/packages/persistence/src/durable-memory-store.ts`：

```typescript
// 新增方法
findCandidatesForDedup(input: {
  readonly subject: string
  readonly statuses: readonly DurableMemoryStatus[]
  readonly recentMs: number
  readonly limit: number
}): Promise<readonly { id: string; content: string; status: DurableMemoryStatus }[]>
```

**SQL 等价**：
```sql
-- findCandidatesForDedup
SELECT memory_id, content, status FROM durable_memories
WHERE subject = $1
  AND status = ANY($2)
  AND created_at > NOW() - INTERVAL '90 days'
ORDER BY created_at DESC
LIMIT $3;
```

**测试**（`durable-memory-store.test.ts` 新增 ~2 cases）：
- 0 candidate (subject mismatch) → []
- N candidates across statuses → all returned
- limit boundary

### 4.3 API 配置（1 文件 + 1 test）

`butler-v5/apps/api/src/dedup-config.ts`（新文件）：

```typescript
export interface DedupConfig {
  readonly enabled: boolean    // threshold > 0
  readonly threshold: number
  readonly recentMs: number     // default 90d
  readonly limit: number        // default 50
}

export function parseDedupConfig(env: NodeJS.ProcessEnv): DedupConfig {
  const threshold = parseFloatSafe(env["BUTLER_V5_MEMORY_DEDUP_THRESHOLD"], 0.85)
  return {
    enabled: threshold > 0,
    threshold,
    recentMs: parseIntSafe(env["BUTLER_V5_MEMORY_DEDUP_RECENT_MS"], 90 * 24 * 3_600_000),
    limit: parseIntSafe(env["BUTLER_V5_MEMORY_DEDUP_LIMIT"], 50),
  }
}
```

### 4.4 调用点更新（3 sites）

`butler-v5/apps/api/src/owner-routes.ts`（2 处 + 1 处 wechat）：

```typescript
// Pattern (applied at each candidate creation site):
import { findSimilarMemories } from "@butler/domain/knowledge/dedup.js"
import { parseDedupConfig } from "./dedup-config.js"

const dedupCfg = parseDedupConfig(process.env)

async function checkDedupOrThrow(opts: {
  store: DurableMemoryStore
  subject: string
  content: string
  bodyForce?: boolean
}): Promise<{ id: string; similarity: number } | null> {
  if (!dedupCfg.enabled || opts.bodyForce) {
    if (opts.bodyForce && dedupCfg.enabled) {
      logger.info(`[memory-dedup] forced duplicate by owner subject=${opts.subject}`)
    }
    return null
  }
  try {
    const result = await findSimilarMemories({
      store: opts.store,
      subject: opts.subject,
      content: opts.content,
      threshold: dedupCfg.threshold,
      statuses: ["candidate", "confirmed", "rejected"],
      recentMs: dedupCfg.recentMs,
      limit: dedupCfg.limit,
    })
    return result.best
  } catch (err) {
    logger.error("[memory-dedup] check failed:", err instanceof Error ? err.message : String(err))
    return null  // fail-open：dedup 失败不能阻止 owner 写
  }
}
```

**3 sites 集成**：
1. `owner-routes.ts:334` — POST /v1/owner/memories：先 `checkDedupOrThrow` → 命中返回 409 with `{ existingMemoryId, similarity }`
2. `owner-routes.ts:625` — 其他 owner candidate 路径：同 pattern
3. `wechat-memory-commands.ts:43` — `/记住` if 创建 status='candidate'：同 pattern（返回 wechat error message）

### 4.5 测试策略（~15 cases）

| Suite | Cases |
|-------|-------|
| `dedup.test.ts` (new, 8) | trigramJaccard 4 (identical / empty / partial / reorder); findSimilarMemories 4 (0/1/edge/limit) |
| `durable-memory-store.test.ts` (扩 2) | findCandidatesForDedup 0/N + limit |
| `dedup-config.test.ts` (new, 3) | default / env override / disabled (threshold=0) |
| `owner-routes.test.ts` (扩 3) | 409 dedup hit / 200 force=true bypass / 200 below threshold |
| `wechat-memory-commands.test.ts` (扩 1) | wechat `/记住` candidate dedup 409 message |
| `tests/architecture/section12-knowledge-memory.test.ts` (扩 1) | §12 G2: `dedup.ts` exists + `trigramJaccard` exported (regex-on-source mirror Case 8) |

### 4.6 边界遵守（DESIGN §段）

- §3 6 硬规则 (D33 lock): 0 触 (Core 接受 store 参数依赖倒置；不 import adapter)
- §20 16 invariant (D26A + D26B): 0 触
- §12 D30 6 cases + D39 G3 + D40 G1: 保留 + 加 1 G2 case
- §12 line 600 "无来源的经验沉积" 不建设: dedup WITH provenance (subject + status) → 不冲突；0 触
- §12 line 593 "默认先用结构化字段" + D30 case #6 lock "默认不启用 embedding": 0 触 (trigram 是字符 n-gram 结构化方法)
- §13 风险与自治: 0 触 (dedup 失败 fail-open 不阻止 owner; 0 grant/approver/policy)
- §14 observability: 0 新 first-class event
- §11.4 / §18 #11 不默认建设: 0 触 (同进程; 不建 broker / 独立 worker)

---

## 5. 文件 ops 清单（预估 ~12 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `packages/domain/src/knowledge/dedup.ts` (new) | +60/-0 | pure fn `trigramJaccard` + `findSimilarMemories` + 2 interfaces |
| `packages/domain/src/knowledge/dedup.test.ts` (new) | +120/-0 | 8 cases |
| `packages/persistence/src/durable-memory-store.ts` | +30/-0 | `findCandidatesForDedup` |
| `packages/persistence/src/durable-memory-store.test.ts` | +60/-0 | 2 cases |
| `apps/api/src/dedup-config.ts` (new) | +30/-0 | env parser |
| `apps/api/src/dedup-config.test.ts` (new) | +50/-0 | 3 cases |
| `apps/api/src/owner-routes.ts` | +50/-0 | 2 sites + checkDedupOrThrow helper |
| `apps/api/src/owner-routes.test.ts` | +90/-0 | 3 new cases |
| `apps/api/src/wechat-memory-commands.ts` | +20/-0 | 1 site |
| `apps/api/src/wechat-memory-commands.test.ts` (if exists) | +30/-0 | 1 new case |
| `tests/architecture/section12-knowledge-memory.test.ts` | +25/-0 | G2 evidence |
| `butler-v5/DESIGN.md` | +12/-0 | §12 audit state 加 G2 行 |
| `docs/superpowers/specs/2026-09-01-durable-memory-dedup-design.md` (this) | +450/-0 | spec |
| `docs/superpowers/plans/2026-09-01-durable-memory-dedup.md` | +300/-0 | plan (plan 阶段产出) |

总预估: ~13 file ops / +1300 prod+test / +60 doc-only

---

## 6. 不做（明确范围外）

- **G4 Layer 1→2 auto-promote**: 违反 §12 line 599 "默认不建设 Dream 两阶段自动巩固"；明确不做
- **G5 跨 project PK recall**: 动 `recall_project_knowledge` 工具语义（`tools.ts:478-479`）；本轮不动
- **embedding-based dedup**: 违反 D30 case #6 lock + §12 line 593；明确不做
- **Cross-subject dedup**: 复杂度爆炸；本轮仅同 subject 内比对
- **Auto-merge similar candidates**（无 provenance auto-clustering）: 违反 §12 line 600 "无来源的经验沉积" 不建设；明确不做
- **Owner-side UI for dedup suggestion**: 本轮只 409 + existingMemoryId；owner UI 后续
- **New Core Port (MemoryDedup 等)**: 与 Channel Port 类比；待 §7 audit 触发；本轮不动
- **Cron / schedule cleanup of dedup leftovers**: dedup 是 creation-time check，无 leftover；本轮不动
- **Auto-archive near-duplicates**: surface 给 owner 由 owner 决策；本轮不动

---

## 7. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-01-durable-memory-dedup.md`（plan 阶段产出）
2. **实施**: 加 dedup.ts + persistence 方法 + dedup-config + 3 调用点 + tests + DESIGN + arch guard 1 case
3. **验证**: typecheck + lint（每 commit 后跑）+ test (production) + test:archived + arch guard pass
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D41-section12-g2-dedup-2026-09-XX.md`（仿 D40 / D39 格式）
5. **commit**: `feat(arch): D41 §12 G2 candidate dedup + trigram Jaccard`
6. **Handoff**: `.blackboard/shifts/2026-09-XX-d41-g2-dedup-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D42: G5 跨 project PK recall（如 owner 真撞）
   - D43+: G4 auto-promote（仅当 owner 改变 §12 设计原则时）

---

## 8. 关联

- D30 §12 audit state (8 cases lock) — `memory/project-fix-D30-section12-knowledge-2026-08-31.md`
- D39 §12 G3 batch UI — `memory/project-fix-D39-section12-batch-ui-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-batch-candidate-ui-design.md`
- D40 §12 G1 candidate expires cleanup — `memory/project-fix-D40-section12-g1-expires-cleanup-2026-09-01.md` + `docs/superpowers/specs/2026-09-01-durable-memory-candidate-expires-cleanup-design.md`
- §12 line 593 + 600 — `DESIGN.md` §12 主规则
- §18 row 3 — `DESIGN.md` line 801（保留 🟡 MVP ship + G3 + G1 状态；G2 不进 §18）
- §3 6 硬规则 (D33 lock) — `memory/project-fix-D33-section3-dependency-2026-08-31.md`
- §20 16 invariant (D26A + D26B) — `memory/project-fix-D26A-section20-batch-A-2026-08-31.md` + `memory/project-fix-D26B-section20-batch-B-2026-08-31.md`
- ExpireCandidatesStore pattern (D40 T3 implementer 创造) — `packages/domain/src/knowledge/candidate-expires.ts:8-16`
- RuntimeStore pattern reference — `packages/domain/src/runtime/store-contract.ts:61-210`

---

**Spec version**: v1 (brainstorming closed 2026-09-01)
**Spec status**: awaiting user review
