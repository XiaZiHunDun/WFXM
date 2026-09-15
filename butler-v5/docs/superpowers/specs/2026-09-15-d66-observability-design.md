# D66 — Observability Plumbing（设计文档）

> 来源：D64 cycle review + D65 final cycle review 推荐 — Path C 第 2 batch = observability。Owner 选 B（T1 only，audit plumbing；T2 acceptance defer D67）。
>
> 范围：D66 = audit emit-side observability foundation。Thread correlationId + add listRecentAuditEvents read method + thread AuditFatigueDetail where fatigue runs。Read-side enables D67 acceptance real verification。
>
> 性质：纯 plumbing（无 owner-facing behavior change）+ new RuntimeStore method。Audit emit signature already supports correlationId optional；T1b is fill-in。

---

## 1. Architecture overview

```
D66 T1 — Audit Observability Plumbing
    │
    ├── T1a: listRecentAuditEvents read method (NEW RuntimeStore contract + impls + test)
    │       │
    │       RuntimeStore contract (packages/domain/src/runtime/store-contract.ts)
    │       ↓
    │       MemoryRuntimeStore impl (packages/persistence/src/memory/runtime-store.ts)
    │       ↓
    │       audit-service wrapper (apps/api/src/audit-service.ts)
    │
    ├── T1b: correlationId threading to ~25 emit sites
    │       │
    │       audit-service / exec-audit / owner-routes/{memories,documents,traces-procedures-tasks,mcp,project-knowledge,conversations-schedule,tasks-run,memories-rollback}.ts / approval-resume.ts
    │       ↓
    │       packages/runtime/{delegate-runtime,approval-runtime,run-lifecycle,capability-boundary}.ts
    │
    └── T1c: AuditFatigueDetail threading (1-2 fatigue-relevant sites)
            │
            wechat-inbound-butler.ts chokepoint (where fatigue runs)
```

### 关键不变量

- D44 y/👌 preserved（无 inline approval 改动）
- D63 audit_event.correlation_id: NOW threaded（closes D63 review #2 carry-from D63）
- D49 UNDO_CHAIN preserved（no chain/undo logic touched）
- D48 4 项产品力 preserved（no owner-facing strings changed）
- Backward compat: AuditEventRecord.correlationId already optional；no schema migration

---

## 2. Components & Data Structures

### 2.1 T1a: `listRecentAuditEvents` read method

**Add to RuntimeStore contract** (`packages/domain/src/runtime/store-contract.ts`):

```typescript
readonly listRecentAuditEvents: (input: {
  readonly actor?: string
  readonly windowMs: number
  readonly conversationId?: string
  readonly limit?: number
}) => Promise<readonly AuditEventRecord[]>
```

**AuditEventRecord type** (already exists in `packages/persistence/src/memory/runtime-store.ts:34`):
```typescript
interface AuditEventRecord {
  readonly auditId: string
  readonly runId: string | null
  readonly conversationId: string | null
  readonly action: string
  readonly subject: string
  readonly detail: Readonly<Record<string, unknown>>
  readonly createdAt: Date
  readonly correlationId?: string | null  // D63 T3 — already optional
}
```

**Implementation in `MemoryRuntimeStore`** (`packages/persistence/src/memory/runtime-store.ts`):
- Query audit_events table with optional actor / conversationId / limit filters
- Sort by createdAt DESC
- Return ReadonlyArray<AuditEventRecord>

**Wrapper in audit-service** (`apps/api/src/audit-service.ts`):
```typescript
export async function listRecentAuditEvents(input: {
  readonly actor?: string
  readonly windowMs: number
  readonly conversationId?: string
  readonly limit?: number
}): Promise<readonly AuditEventRecord[]> {
  return store.listRecentAuditEvents(input)
}
```

### 2.2 T1b: correlationId threading

For each emit site, pass `correlationId: ctx.runId ?? ctx.correlationId` from existing wiring context.

**Emit sites** (~25, from grep):
- `apps/api/src/audit-service.ts:12`
- `apps/api/src/exec-audit.ts:53`
- `apps/api/src/owner-routes/tasks-run.ts:37`
- `apps/api/src/owner-routes/project-knowledge.ts:116, 159`
- `apps/api/src/owner-routes/memories.ts:138, 174, 227, 348, 382`
- `apps/api/src/owner-routes/memories-rollback.ts:120`
- `apps/api/src/owner-routes/documents.ts:97, 138, 164`
- `apps/api/src/owner-routes/traces-procedures-tasks.ts:92, 157, 192`
- `apps/api/src/owner-routes/mcp.ts:98`
- `apps/api/src/owner-routes/conversations-schedule.ts:78`
- `apps/api/src/approval-resume.ts:457, 497`
- `packages/runtime/src/{delegate-runtime,approval-runtime,run-lifecycle,capability-boundary}.ts` (~5 sites)

**Pattern for each site:**
```typescript
// Before:
await wiring.runtimeStore.appendAuditEvent({
  auditId: makeLoopId(),
  runId: ctx.runId ?? null,
  conversationId: ctx.conversationId ?? null,
  action: "...",
  subject: "...",
  detail: { ... },
  createdAt: new Date(),
})

// After:
await wiring.runtimeStore.appendAuditEvent({
  auditId: makeLoopId(),
  runId: ctx.runId ?? null,
  conversationId: ctx.conversationId ?? null,
  action: "...",
  subject: "...",
  detail: { ... },
  createdAt: new Date(),
  correlationId: ctx.runId ?? ctx.correlationId ?? null,  // ← NEW
})
```

### 2.3 T1c: AuditFatigueDetail threading

**Sites where fatigue runs:**
- `apps/api/src/wechat-inbound-butler.ts:executeTool` chokepoint（after D65 T1 extraction）

**Pattern:**
```typescript
// Import AuditFatigueDetail type
import type { AuditFatigueDetail } from "./lib/fatigue/audit-event"

// In executeTool, after fatigue decision:
const detail: AuditFatigueDetail = {
  fatigue_signal: toolDecision.kind !== "allow" 
    ? { count: 3, window_seconds: 60, last_n_actions: [...] }
    : undefined,
  cooldown_applied: toolDecision.kind === "cooldown" 
    ? { duration_ms: toolDecision.durationMs }
    : undefined,
  checklist_required: toolDecision.kind === "checklist",
}

await wiring.runtimeStore.appendAuditEvent({
  auditId: makeLoopId(),
  ...
  detail: { ...otherDetail, ...detail },
})
```

---

## 3. Data Flow

### T1a — listRecentAuditEvents

```
owner-routes/audit-fatigue.ts (or new consumer)
    ↓
audit-service.listRecentAuditEvents({ actor, windowMs, conversationId, limit })
    ↓
RuntimeStore.listRecentAuditEvents(input)
    ↓
audit_events table query (filtered + sorted DESC by createdAt)
    ↓
returns ReadonlyArray<AuditEventRecord>
```

### T1b — correlationId threading

Per emit site: existing audit_service.appendAuditEvent call site gets correlationId added. No new data flow — just optional field populated from wiring context.

### T1c — AuditFatigueDetail threading

```
wechat-inbound-butler.ts executeTool chokepoint
    ↓
executeToolWithFatigue(toolName, toolArgs, reader) returns ToolExecutionDecision
    ↓
Build AuditFatigueDetail from toolDecision
    ↓
Pass detail: { ...otherDetail, ...auditFatigueDetail } to appendAuditEvent
    ↓
audit_events table row has detail.fatigue_signal / detail.cooldown_applied / detail.checklist_required
```

---

## 4. Error Handling

| Failure | T1a behavior | T1b/T1c behavior |
|---|---|---|
| MemoryRuntimeStore throws | propagate to caller (same as existing appendAuditEvent) | N/A |
| query audit_events fails | log + return empty array (graceful degrade per D48 §4.3) | N/A |
| correlationId undefined | already optional; no breakage | N/A |
| Existing appendAuditEvent tests | unchanged (optional field) | regression-safe |

---

## 5. Testing

### 5.1 Unit (T1a)

**File:** `apps/api/src/audit-service.test.ts` (extend existing)

| Case | Description | Assertion |
|---|---|---|
| L1 | listRecentAuditEvents with actor filter | returns matching events |
| L2 | listRecentAuditEvents with windowMs filter | returns events within window |
| L3 | listRecentAuditEvents with limit | returns ≤ limit events |
| L4 | listRecentAuditEvents on empty store | returns empty array |

### 5.2 Unit (T1a + 5.3 Unit T1c — combined in audit-event.test.ts extension)

| Case | Description | Assertion |
|---|---|---|
| L5 | audit-event shape accepts AuditFatigueDetail embedded in `detail` | structural compatibility |

### 5.3 Existing tests — no regression

All existing tests must pass unchanged (1994 pass baseline; 5 pre-existing fail unchanged; 0 new fail).

### 5.4 Acceptance — unchanged

44/44 unchanged (observability batch is infra-only; no scenario changes).

---

## 6. Files Changed (预估)

| Track | File | Change |
|---|---|---|
| T1a | `packages/domain/src/runtime/store-contract.ts` | +listRecentAuditEvents method (~10 lines) |
| T1a | `packages/persistence/src/memory/runtime-store.ts` | +listRecentAuditEvents impl (~20 lines) |
| T1a | `apps/api/src/audit-service.ts` | +listRecentAuditEvents wrapper (~10 lines) |
| T1a | `apps/api/src/audit-service.test.ts` | +4 unit tests |
| T1b | ~12 apps/api/src files | +correlationId per emit site (~25 sites, 1 line each) |
| T1b | ~4 packages/runtime/src files | +correlationId per emit site (~5 sites, 1 line each) |
| T1c | `apps/api/src/wechat-inbound-butler.ts` | +AuditFatigueDetail at chokepoint (~20 lines) |
| T1c | `apps/api/src/lib/fatigue/audit-event.test.ts` | +1-2 unit tests |
| post-fix | `.audit/D66/{summary.md, protocol-compliance.md}` | NEW |
| post-fix | `MEMORY.md` | Current State update |

预估 net: +150/-30 lines (mostly new method + threading additions).

---

## 7. v5 DESIGN alignment

- §7.1 Ports: new RuntimeStore port method (listRecentAuditEvents); existing audit port updated
- §10.4 Sandbox: no sandbox changes
- §11.3 Approval: no approval flow changes
- §12 Knowledge: no durable memory changes
- §18 Trigger guard: owner-triggered Path C batch launch（explicit）

---

## 8. Lessons / 注意事项

- **T1a listRecentAuditEvents**: minimum viable — supports the (actor?, windowMs, conversationId?, limit?) filter combo used by D67 acceptance + any future replay integration
- **T1b correlationId threading**: pass `ctx.runId ?? ctx.correlationId ?? null` from existing wiring context — no new plumbing needed
- **T1c AuditFatigueDetail threading**: thread to chokepoint only (1 site initially); future sites can opt-in
- **Backward compat**: AuditEventRecord.correlationId is already optional (D63 T3); no migration needed
- **No schema changes**: detail field is already Readonly<Record<string, unknown>> (D63 contract) — AuditFatigueDetail embeds there

---

## 9. Acceptance Gates (N=3 fresh verify)

| Gate | Baseline | D66 expected |
|---|---|---|
| lint | 0 fatigue warnings | 0 unchanged |
| typecheck | 0 errors | 0 new |
| test:full | 1994 pass / 5 pre-existing fail | 1994+ pass, 5 unchanged, 0 new fail |
| acceptance | 44/44 | 44/44 unchanged |
| methodology | 13/13 | 13/13 unchanged |
| knip | 0 new deadcode | 0 new |

---

## 10. Out of scope (D67+)

- F1/F2/F3 acceptance real verification (runtimeStore.createStep integration + harness audit event writes)
- 60+ scenarios expansion + arch boundary 收口
- D62 T2/T3/T5 larger partial reverts
- `runButlerLoopBody` further god-fn splits

---

**End D66 design doc.**
