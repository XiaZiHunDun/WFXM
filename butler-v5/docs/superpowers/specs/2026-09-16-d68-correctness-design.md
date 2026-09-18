# D68 — Correctness Fix + Tech Debt Cleanup（设计文档）

> 来源：D67 cycle review 推荐 Tier 1（必须修）+ Tier 2（carry-over tech debt）— D68 batch 1。Owner 选 Balanced。
>
> 范围：D68 = harness bug fix（highest-priority correctness）+ D64 reader-swap（subagentAuditAsFatigueReader → listRecentAuditEvents）+ spec §2.2 drift fix（doc update）。
>
> 性质：Tier 1 critical correctness fix + Tier 2 tech debt cleanup。Tier 3/4 follow-ups defer D69+。

---

## 1. Architecture overview

```
D68 — Correctness Fix + Tech Debt Cleanup
    │
    ├── T1: Harness bug fix (Tier 1 — must-fix)
    │       │
    │       tests/acceptance/scenarios/realistic.test.ts:202-229
    │       ↓
    │       Capture runMultiRound result + assert result.passed === true
    │       ↓
    │       Future acceptance failures will no longer silent pass
    │
    ├── T2a: D64 reader swap (Tier 2a — tech debt)
    │       │
    │       apps/api/src/wechat-inbound-butler.ts:62-78 (subagentAuditAsFatigueReader)
    │       ↓
    │       Switch from readRecentSubagentAudit(env) [JSONL]
    │       to store.listRecentAuditEvents({ windowMs, limit }) [audit_events table]
    │       ↓
    │       F1/F2/F3 acceptance now exercises REAL audit_events read path
    │
    ├── T2b: Spec drift fix (Tier 2b — doc update)
    │       │
    │       docs/superpowers/specs/2026-09-16-d67-acceptance-design.md §2.2
    │       ↓
    │       Remove "JSONL bridge workaround" note
    │       ↓
    │       Spec now matches reality (T2a reader swap complete)
    │
    └── post-fix: drift closure + raw findings archive
```

### 关键不变量

- D44 y/👌 preserved（harness bug fix 不动 inline approval flow）
- D63 audit_event preserved（T2a reader swap 改 source 不改 schema）
- D49 UNDO_CHAIN preserved（no chain logic touched）
- D48 4 项产品力 preserved（no owner-facing strings changed）

---

## 2. Components & Data Structures

### 2.1 T1: Harness bug fix

**File:** `tests/acceptance/scenarios/realistic.test.ts:202-229`

**Before:**
```typescript
const itBody = async () => {
  // ... state init ...
  await runMultiRound(
    scenario,
    ctx,
    { iterations: 3, scenarioId: scenario.id }
  )
  // runMultiRound aggregation.all 已校验 3 round 全 pass → 走到这里说明全过
  metrics.push({
    scenarioId: scenario.id,
    passed: true,
    // ...
  })
}
```

**After:**
```typescript
const itBody = async () => {
  // ... state init ...
  const result = await runMultiRound(
    scenario,
    ctx,
    { iterations: 3, scenarioId: scenario.id }
  )
  expect(result.passed).toBe(true)  // ← D68 T1 critical fix
  metrics.push({
    scenarioId: scenario.id,
    passed: result.passed,
    // ...
  })
}
```

**Why this matters:** `multi-round.ts:78-79` explicit comment: "helper must NOT throw on aggregation.all failure — caller reads `result.passed`". Current realistic.test.ts:202 ignores this contract → silent pass on failure.

### 2.2 T2a: D64 reader swap

**File:** `apps/api/src/wechat-inbound-butler.ts:62-78`

**Before:**
```typescript
export function subagentAuditAsFatigueReader(env: NodeJS.ProcessEnv): AuditLogReader {
  return {
    readRecent: async (windowMs: number) => {
      const cutoff = Date.now() - windowMs
      const entries = readRecentSubagentAudit(50, env)  // ← JSONL log source
      return entries.filter((e) => Date.parse(e.ts) >= cutoff)
    },
  }
}
```

**After:**
```typescript
export function subagentAuditAsFatigueReader(env: NodeJS.ProcessEnv, runtimeStore: RuntimeStore): AuditLogReader {
  return {
    readRecent: async (windowMs: number) => {
      const events = await runtimeStore.listRecentAuditEvents({
        windowMs,
        limit: 100,  // D66 T1a default
      })
      // Map AuditEventRecord → AuditEventSummary for policy layer compatibility
      return events.map(e => ({
        event_id: e.auditId,
        tool_name: e.subject,
        actor: e.actor ?? 'owner',
        ts: e.createdAt.getTime(),
        decision: 'allow' as const,
      }))
    },
  }
}
```

**Call site update:** Need to thread `runtimeStore` through to where `subagentAuditAsFatigueReader` is called.

### 2.3 T2b: Spec drift fix

**File:** `docs/superpowers/specs/2026-09-16-d67-acceptance-design.md` §2.2

**Before:** Contains "JSONL bridge workaround" note (lines 106-113 in current version).

**After:** Remove the JSONL bridge note since T2a reader swap makes it obsolete.

---

## 3. Data Flow

### T1 — Harness bug fix

```
Acceptance scenario executes
    ↓
runMultiRound runs scenario N=3 times
    ↓
Returns MultiRoundResult { passed: bool, rounds: [...] }
    ↓
realistic.test.ts asserts result.passed === true  ← CRITICAL FIX
    ↓
If false → test FAILS (no more silent pass)
```

### T2a — D64 reader swap

```
FatigueSignal needs audit data
    ↓
subagentAuditAsFatigueReader(env, runtimeStore).readRecent(windowMs)
    ↓
runtimeStore.listRecentAuditEvents({ windowMs, limit })  ← audit_events table
    ↓
Map AuditEventRecord → AuditEventSummary (for policy layer compat)
    ↓
FatigueSignal.computeFatigueSignal(reader) returns count + last_n_actions
```

---

## 4. Error Handling

| Failure | T1 behavior | T2a behavior | T2b behavior |
|---|---|---|---|
| scenario assertion fails | `expect(result.passed).toBe(true)` throws → test fails (correct!) | N/A | N/A |
| `runtimeStore.listRecentAuditEvents` throws | N/A | propagate (existing pattern) | N/A |
| `audit_events` table doesn't exist (test env) | N/A | graceful empty array | N/A |
| Spec doc typo | N/A | N/A | trivial fix |

---

## 5. Testing

### 5.1 Unit (T1)

**File:** `tests/acceptance/scenarios/realistic.test.ts`

| Case | Description | Assertion |
|---|---|---|
| U1 | All 52 acceptance scenarios pass with new assertion | 52/52 pass |
| U2 | Failure scenario (intentionally fail) returns `result.passed === false` | assertion throws → test fails correctly |
| U3 | Existing 52 scenarios unchanged | no regression in metrics |

### 5.2 Unit (T2a)

**File:** `apps/api/src/wechat-inbound-butler.test.ts`

| Case | Description | Assertion |
|---|---|---|
| U4 | F1 acceptance scenario now triggers REAL cooldown via audit_events | cooldown durationMs=3000 verified |
| U5 | F2 acceptance scenario now exercises REAL pending step | bridge reply "已升级" |
| U6 | F3 acceptance scenario now reads REAL audit data | sequences non-empty |

### 5.3 No regression

All existing tests must pass unchanged (baseline: 2015 pass / 5 pre-existing fail / 52 acceptance).

---

## 6. Files Changed (预估)

| Track | File | Change |
|---|---|---|
| T1 | `tests/acceptance/scenarios/realistic.test.ts` | +5 / -3 lines (capture + assert) |
| T2a | `apps/api/src/wechat-inbound-butler.ts` | +15 / -10 lines (reader swap + call site) |
| T2a | `apps/api/src/wechat-inbound-butler.test.ts` | 0 new (existing F1/F2/F3 tests now verify REAL cooldown) |
| T2b | `docs/superpowers/specs/2026-09-16-d67-acceptance-design.md` | -10 lines (remove JSONL note) |
| post-fix | `.audit/D68/{summary.md, protocol-compliance.md}` | NEW |
| post-fix | `MEMORY.md` | Current State update |

预估 net: -50 / +30 lines (mostly net removal of workaround code + spec cleanup).

---

## 7. v5 DESIGN alignment

- §7.1 Ports: T2a uses existing RuntimeStore.listRecentAuditEvents (D66 T1a)
- §10.4 Sandbox: no sandbox changes
- §11.3 Approval: T1 harness fix doesn't change approval flow
- §12 Knowledge: no durable memory changes
- §18 Trigger guard: owner-triggered D68 launch

---

## 8. Lessons / 注意事项

- **T1 critical fix**: Without this, future acceptance failures ship silently. Highest priority.
- **T2a reader swap**: Real fix to underlying D64 carry-over tech debt. After this, spec §2.2 becomes accurate.
- **T2b doc update**: After T2a, JSONL bridge workaround is obsolete. Remove the note to prevent future confusion.
- **No production code changes** beyond reader swap (T2a) — T1 is test-only, T2b is doc-only
- **`[MANUAL-OVERRIDE]`** likely needed for `wechat-inbound-butler.ts` (protected file per D60 protocol)

---

## 9. Acceptance Gates (N=3 fresh verify)

| Gate | Baseline | D68 expected |
|---|---|---|
| lint | 0 fatigue warnings | 0 unchanged |
| typecheck | 0 errors (4 projects) | 0 new |
| test:full | 2015 pass / 5 pre-existing | 2015+ pass, 5 unchanged, 0 new |
| acceptance | 52/52 | 52/52 (now exercises REAL audit_events via T2a) |
| methodology | 13/13 | 13/13 unchanged |
| knip | 0 new deadcode | 0 new |

---

## 10. Out of scope (D69+)

- T1c fatigue_signal coverage
- T1b owner-routes correlation
- D62 T2/T3/T5 partial reverts
- Schema migration: dedicated `actor` column — **closed by D71 T1** (migration 0014 + AuditFatigueReaderOptions.columnActor; D72 T1 enables columnActor: true at 2 production call sites)
- `runButlerLoopBody` further god-fn splits
- Arch boundary 收口

---

**End D68 design doc.**
