# D65 — Health Batch（设计文档）

> 来源：D64 cycle review 推荐 Path C 第 1 batch — god-fn split + ESLint cleanup + D63 T2 partial revert。Owner 选 Balanced（推荐）。
>
> 范围：D65 = Health 维度 5 ships（T1-T5 + post-fix）。D66 = observability，D67 = acceptance。Path C 3-batch 渐进 ship。
>
> 性质：纯 refactor + code health，不改 owner-facing behavior；4 项 locked invariants 全部 preserved。

---

## 1. Architecture overview

```
D65 Health Batch
    ├── T1: runButlerLoopBody god-fn split
    │       ↓
    │   extract fatigue decision block (D64 wiring ~50 lines)
    │       ↓
    │   to lib/fatigue/execute-tool-with-fatigue.ts (NEW)
    │       ↓
    │   runButlerLoopBody becomes thin coordinator
    │
    ├── T2: 4 owner-routes files god-fn partial split
    │       ↓
    │   memories.ts (503) / traces-procedures-tasks.ts (255) /
    │   documents.ts (255) / approvals-runs.ts (222)
    │       ↓
    │   extract largest handler functions to per-route files
    │
    ├── T3: ESLint cleanup 7 warnings in fatigue/*.ts
    │       ↓
    │   6× array-type: ReadonlyArray<T> → readonly T[]
    │   1× unused-vars: ctx → _ctx (or remove)
    │
    ├── T4: D63 T2 owner-jargon 5 sites revert
    │       ↓
    │   swap internal jargon → owner-friendly via owner-jargon.ts
    │   update reply-string tests same batch (per memory)
    │
    ├── T5: remaining minor (knip clean + any D62/D63 T5 partial)
    │
    └── post-fix: drift closure + raw findings archive
```

### 关键不变量 (全部 preserved)

- D44 y/👌 1-token — fatigue check BEFORE y（不破坏 T5 acceptance flow）
- D63 audit_event.correlation_id — T4 不动 audit emit
- D49 UNDO_CHAIN — T1 提取不触碰 undo 逻辑
- D48 4 项产品力 — owner-facing strings 已 jargon-free，T4 revert 强化而非弱化
- ESLint `array-type` convention: `readonly T[]` not `ReadonlyArray<T>`

---

## 2. Components & Data Structures

### 2.1 T1: `execute-tool-with-fatigue.ts` (NEW)

**File:** `apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts`

```typescript
/**
 * D65 — Extract fatigue decision block from runButlerLoopBody (D64 wiring).
 *
 * Pre-condition: tool call has cleared inline-approval y/👌
 * (D44 1-token invariant preserved — fatigue check happens BEFORE y).
 *
 * Returns the tool-execution decision after fatigue mitigation:
 * - `allow` → execute tool directly
 * - `cooldown` → render wait prompt + sleep duration_ms
 * - `checklist` → throw RunPauseForApproval with rendered prompt
 */
export async function executeToolWithFatigue(
  toolName: string,
  toolArgs: Readonly<Record<string, unknown>>,
  reader: AuditLogReader,
  ctx: ChannelContext,
): Promise<ToolExecutionDecision>

export type ToolExecutionDecision =
  | { readonly kind: 'allow' }
  | { readonly kind: 'cooldown'; readonly durationMs: number }
  | { readonly kind: 'checklist'; readonly items: readonly string[] }
```

**Caller changes:** `wechat-inbound-butler.ts` `runButlerLoopBody` calls `executeToolWithFatigue` instead of inline fatigue decision block. ~50 lines removed from caller; ~50 lines added to new file.

### 2.2 T2: 4 owner-routes partial splits

**Candidates (sorted by line count):**
- `apps/api/src/owner-routes/memories.ts` (503 lines) — extract largest handler(s)
- `apps/api/src/owner-routes/traces-procedures-tasks.ts` (255 lines)
- `apps/api/src/owner-routes/documents.ts` (255 lines)
- `apps/api/src/owner-routes/approvals-runs.ts` (222 lines)

**Split pattern (mirrors existing per-file convention):**
- Identify largest handler function in each file (>50 lines)
- Extract to new file (e.g., `owner-routes/memories-{handler}.ts`)
- Re-export from original file (backward compat)
- Existing tests still cover behavior; no test changes needed

### 2.3 T3: ESLint cleanup

**6 array-type fixes:**

| File | Line | Before | After |
|---|---|---|---|
| checklist.ts | 1, 8, 17 | `ReadonlyArray<string>` | `readonly string[]` |
| signal.ts | 14, 20 | `ReadonlyArray<AuditEventSummary>` | `readonly AuditEventSummary[]` |
| signal.test.ts | 5 | `ReadonlyArray<AuditEventSummary>` | `readonly AuditEventSummary[]` |

**1 unused-vars fix:**

| File | Line | Before | After |
|---|---|---|---|
| inline-approval-wiring.ts | 28 | `ctx: ChannelContext` (never used) | `_ctx: ChannelContext` (or remove if unneeded) |

**Fix strategy:** Use `pnpm eslint --fix` for auto-fixable array-type. Manual review for unused-vars (decide prefix vs remove).

### 2.4 T4: D63 T2 owner-jargon 5 sites revert

**Files identified with owner-jargon usage** (6 candidates, pick 5):
- `apps/api/src/wechat-task-commands.ts`
- `apps/api/src/dev-quality-gate.ts`
- `apps/api/src/wechat-task-digest-reply.ts`
- `apps/api/src/wechat-sweeper-notify.ts`
- `apps/api/src/wechat-run-notify.ts`
- `apps/api/src/wechat-memory-commands.ts`

**Revert pattern:** Use existing `apps/api/src/owner-jargon.ts` helper to swap internal jargon (e.g., "approve", "audit", "fatigue", "policy") to owner-facing language. Update corresponding `.test.ts` reply-string assertions in same batch (per memory `feedback-d-batch-reply-string-test-update-batch`).

### 2.5 T5: knip + D62/D63 minor partial

**knip:** Verify 0 new deadcode after T1-T4. Sweep if any introduced.

**D62/D63 T5 partial:** Any remaining minor sites not closed in earlier batches — sweep pass.

---

## 3. Data Flow (T1 only — others are file-level refactors)

```
wechat-inbound-butler.ts:runButlerLoopBody
    ↓
    await inlineApprovalResolved (existing)
    ↓
    decision = await executeToolWithFatigue(toolName, toolArgs, reader, ctx)  ← NEW extracted call
    ↓
    switch decision.kind:
      case 'allow':
        return await toolExecutor.execute(toolName, toolArgs)
      case 'cooldown':
        render wait prompt + sleep decision.durationMs
        return await toolExecutor.execute(toolName, toolArgs)
      case 'checklist':
        throw new RunPauseForApproval({ renderedPrompt: decision.items.join('\n') })
```

**Key invariants preserved:**
- Fatigue check happens AFTER inline-approval y/👌 resolution (D44 1-token preserved)
- D63 audit_event emit pattern unchanged (no audit emit added in T1)
- D49 UNDO_CHAIN not invoked (no undo logic in extracted function)

---

## 4. Error Handling

| Failure | T1 behavior | T2-T5 behavior |
|---|---|---|
| Reader throws | `degraded: true` → policy `allow` → tool executes (D48 §4.3) | unchanged |
| ESLint `--fix` fails on a file | manual fix per warning type | N/A |
| Existing test fails after split | revert the split + investigate | N/A |
| D63 T2 revert breaks reply-string test | update test same batch (memory) | N/A |

**Critical:** T1 extraction must not change observable behavior. All D64 acceptance scenarios (44/44) must still pass without modification.

---

## 5. Testing

### 5.1 Unit (T1 only — others reuse existing tests)

**File:** `apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts` (NEW)

| Case | Description | Assertion |
|---|---|---|
| F1 | `allow` decision → execute tool | `result.kind === 'allow'`, tool executed |
| F2 | `cooldown` decision → return duration | `result.kind === 'cooldown'`, `durationMs === 3000` |
| F3 | `checklist` decision → return items | `result.kind === 'checklist'`, items.length === 2 |

### 5.2 Integration (cross-channel, reuse D64 cross-channel.test.ts)

No new tests — T1 extraction is internal refactor. Existing cross-channel.test.ts (8 tests) still cover the wiring.

### 5.3 ESLint gate

`pnpm eslint apps/api/src/lib/fatigue/` → 0 warnings (was 7)

### 5.4 D63 T2 revert tests

5 sites updated → corresponding `.test.ts` reply-string assertions updated same batch (per `feedback-d-batch-reply-string-test-update-batch`).

### 5.5 No regression

- All existing tests pass (1990 pass / 6 pre-existing fail / 0 new)
- Acceptance 44/44 unchanged
- Methodology 13/13 unchanged
- knip 0 new deadcode

---

## 6. Files Changed (预估)

| Track | File | Change |
|---|---|---|
| T1 | `apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts` | NEW (~60 lines) |
| T1 | `apps/api/src/wechat-inbound-butler.ts` | -50 lines (extract block) |
| T1 | `apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts` | NEW (~40 lines, 3 tests) |
| T2 | `apps/api/src/owner-routes/memories.ts` | extract largest handler (~50-100 lines removed) |
| T2 | `apps/api/src/owner-routes/memories-{handler}.ts` | NEW (extracted handler) |
| T2 | (similar for traces-procedures-tasks / documents / approvals-runs) | pattern × 3 |
| T3 | `apps/api/src/lib/fatigue/checklist.ts` | -3 lines +0 (ReadonlyArray → readonly) |
| T3 | `apps/api/src/lib/fatigue/signal.ts` | -2 lines +0 |
| T3 | `apps/api/src/lib/fatigue/signal.test.ts` | -1 line +0 |
| T3 | `apps/api/src/lib/fatigue/inline-approval-wiring.ts` | -1 char (ctx → _ctx) |
| T4 | 5 of 6 wechat-*.ts files | reply-string revert |
| T4 | 5 corresponding *.test.ts files | assertion update same batch |
| T5 | (sweep pass) | minor cleanup if any |
| post-fix | `.audit/D65/{summary.md, protocol-compliance.md}` | NEW |
| post-fix | MEMORY.md | update Current State |

预估 net: -150 / +250 lines (split + extraction reduce nesting)

---

## 7. v5 DESIGN alignment

- §7.1 Ports: no new ports (T1 returns decision type extracted from existing types)
- §10.4 Sandbox: no sandbox changes
- §11.3 Approval: inline-approval decision logic unchanged (T1 only re-organizes)
- §12 Knowledge: no durable memory changes
- §18 Trigger guard: D65 is owner-approved Path C launch (not撞点-driven, owner explicit ask)

---

## 8. Lessons / 注意事项

- **T1 extraction must preserve observable behavior** — 44/44 acceptance is the gate
- **T3 ESLint cleanup** is mechanical; use `--fix` where possible
- **T4 reply-string updates must ship same batch** (memory `feedback-d-batch-reply-string-test-update-batch`)
- **D62/D63 T5 partial reverts** — scope tightly; defer larger sites to D66+
- **No new audit_event writes** (D63 audit pipeline unchanged)
- **No new dependencies** (pure code refactor)

---

## 9. Acceptance Gates (N=3 fresh verify)

| Gate | Baseline | D65 expected |
|---|---|---|
| lint (fatigue/*.ts) | 7 warnings | 0 warnings |
| typecheck | 0 errors | 0 new errors |
| test:full | 1990 pass 6 pre-existing fail | 1990+ pass, 6 unchanged, 0 new fail |
| acceptance | 44/44 | 44/44 unchanged |
| methodology | 13/13 | 13/13 unchanged |
| knip | 0 deadcode | 0 new deadcode |

---

## 10. Out of scope (D66+)

- Audit event write-side plumbing (~15-20 emit sites)
- D63 correlation_id threading
- F1/F2/F3 acceptance real verification (runtimeStore.createStep + audit_events read method)
- 60+ scenarios expansion
- arch boundary 收口
- D62 T2/T3/T5 larger partial reverts (deferred to D66/D67)

---

**End D65 design doc.**
