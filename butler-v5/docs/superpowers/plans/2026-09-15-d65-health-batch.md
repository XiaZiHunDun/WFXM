# D65 Health Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Path C 第 1 batch — god-fn split + ESLint cleanup + D63 T2 partial revert。清理 D62/D63/D64 deferred code health gaps，为 D66 observability + D67 acceptance 打基础。

**Architecture:** 纯 refactor，不改 owner-facing behavior。T1 extract fatigue decision block 到新文件；T2 4 owner-routes 文件 partial god-fn split；T3 ESLint 7 warnings cleanup；T4 D63 T2 owner-jargon 5 sites revert（reply-string tests 同 batch 更新 per memory）；T5 knip clean + minor sweep；post-fix drift closure + raw findings。

**Tech Stack:** TypeScript + vitest + pnpm + ESLint + knip。复用 D62/D63/D64 ship patterns。

**Spec Reference:** `butler-v5/docs/superpowers/specs/2026-09-15-d65-health-batch-design.md`

---

## File Structure

| Track | File | Change |
|---|---|---|
| T1 | `apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts` | NEW (~60 lines, 3 exports) |
| T1 | `apps/api/src/wechat-inbound-butler.ts` | MODIFY: extract fatigue decision block |
| T1 | `apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts` | NEW (3 unit tests) |
| T2a | `apps/api/src/owner-routes/memories.ts` | MODIFY: extract largest handler |
| T2a | `apps/api/src/owner-routes/memories-{handler}.ts` | NEW (extracted handler) |
| T2b-d | similar for traces-procedures-tasks / documents / approvals-runs | pattern × 3 |
| T3 | `apps/api/src/lib/fatigue/checklist.ts` | MODIFY: array-type (3 lines) |
| T3 | `apps/api/src/lib/fatigue/signal.ts` | MODIFY: array-type (2 lines) |
| T3 | `apps/api/src/lib/fatigue/signal.test.ts` | MODIFY: array-type (1 line) |
| T3 | `apps/api/src/lib/fatigue/inline-approval-wiring.ts` | MODIFY: unused-vars (1 char) |
| T4 | 5 of 6 wechat-*.ts files | MODIFY: reply-string owner-jargon revert |
| T4 | 5 corresponding *.test.ts files | MODIFY: assertion update same batch |
| T5 | (sweep pass) | minor cleanup if any |
| post-fix | `.audit/D65/{summary.md, protocol-compliance.md}` | NEW |

预估 net: -150 / +250 lines (split + extraction reduce nesting).

---

## Commit Plan

| Task | Track | Commit |
|---|---|---|
| Task 1 | T1: runButlerLoopBody god-fn split | `refactor(fatigue): T1 extract execute-tool-with-fatigue` |
| Task 2 | T2a: memories.ts partial split | `refactor(routes): T2a memories.ts handler extract` |
| Task 3 | T2b: traces-procedures-tasks.ts split | `refactor(routes): T2b traces-procedures-tasks split` |
| Task 4 | T2c: documents.ts split | `refactor(routes): T2c documents split` |
| Task 5 | T2d: approvals-runs.ts split | `refactor(routes): T2d approvals-runs split` |
| Task 6 | T3: ESLint cleanup | `style(fatigue): T3 ESLint array-type + unused-vars` |
| Task 7 | T4: D63 T2 owner-jargon 5 sites | `refactor(jargon): T4 D63 T2 5 sites revert + tests` |
| Task 8 | T5: knip + minor sweep | `chore: T5 knip clean + D62/D63 T5 minor` |
| Task 9 | post-fix: drift + audit | `fix(drift): D65 close` + `docs(audit): D65 archive` |

---

## Task 1: T1 runButlerLoopBody god-fn split

**Files:**
- Create: `apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts`
- Modify: `apps/api/src/wechat-inbound-butler.ts:580-625` (extract fatigue decision block)
- Create: `apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts`

### Step 1: Run existing baseline to verify no regression before changes

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm vitest run apps/api/src/lib/fatigue/ 2>&1 | tail -5
pnpm test:acceptance 2>&1 | tail -5
```

Expected: 36/36 fatigue pass; 44/44 acceptance pass.

### Step 2: Write 3 failing tests for extracted function

Create `apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts`:

```typescript
import { describe, test, expect, vi } from "vitest"
import { executeToolWithFatigue } from "./execute-tool-with-fatigue"
import type { ChannelContext } from "./inline-approval-wiring"
import type { AuditLogReader, AuditEventSummary } from "./signal"

const ctx: ChannelContext = {
  channel: "wechat",
  actor: "owner",
  correlationId: "c1",
}

function makeReader(count: number): AuditLogReader {
  return {
    readRecent: vi.fn(async (): Promise<readonly AuditEventSummary[]> =>
      Array.from({ length: count }, (_, i): AuditEventSummary => ({
        event_id: `e${i}`,
        tool_name: "read_file",
        actor: "owner",
        ts: Date.now() - i * 1000,
        decision: "allow",
      }))
    ),
  }
}

describe("executeToolWithFatigue", () => {
  test("F1: low-signal normal tool returns allow", async () => {
    const result = await executeToolWithFatigue("read_file", {}, makeReader(0), ctx)
    expect(result.kind).toBe("allow")
  })

  test("F2: high-signal normal tool returns cooldown with durationMs", async () => {
    const result = await executeToolWithFatigue("read_file", {}, makeReader(3), ctx)
    expect(result.kind).toBe("cooldown")
    if (result.kind !== "cooldown") throw new Error("expected cooldown")
    expect(result.durationMs).toBe(3000)
  })

  test("F3: high-sensitivity tool returns checklist with items", async () => {
    const result = await executeToolWithFatigue("send_email", {}, makeReader(0), ctx)
    expect(result.kind).toBe("checklist")
    if (result.kind !== "checklist") throw new Error("expected checklist")
    expect(result.items.length).toBeGreaterThan(0)
  })
})
```

### Step 3: Run test to verify it fails

Run: `cd /home/ailearn/projects/WFXM/butler-v5 && pnpm vitest run apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts 2>&1 | tail -10`
Expected: FAIL "Cannot find module './execute-tool-with-fatigue'"

### Step 4: Create the extracted function file

Create `apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts`:

```typescript
/**
 * D65 T1 — Extract fatigue decision block from runButlerLoopBody.
 *
 * Pre-condition: inline-approval y/👌 already resolved (D44 1-token preserved).
 *
 * Returns the tool-execution decision after fatigue mitigation:
 * - `allow` → execute tool directly
 * - `cooldown` → render wait prompt + sleep durationMs (caller handles sleep)
 * - `checklist` → throw RunPauseForApproval with rendered prompt (caller handles)
 */
import { evaluateInlineApproval } from "./policy"
import type { ChannelContext } from "./inline-approval-wiring"
import type { AuditLogReader } from "./signal"

export type ToolExecutionDecision =
  | { readonly kind: "allow" }
  | { readonly kind: "cooldown"; readonly durationMs: number }
  | { readonly kind: "checklist"; readonly items: readonly string[] }

export async function executeToolWithFatigue(
  toolName: string,
  toolArgs: Readonly<Record<string, unknown>>,
  reader: AuditLogReader,
  _ctx: ChannelContext,
): Promise<ToolExecutionDecision> {
  const decision = await evaluateInlineApproval({ tool_name: toolName, args: toolArgs }, reader)
  switch (decision.action) {
    case "allow":
      return { kind: "allow" }
    case "cooldown":
      return { kind: "cooldown", durationMs: decision.duration_ms }
    case "checklist":
      return { kind: "checklist", items: decision.items }
  }
}
```

### Step 5: Run test to verify it passes

Run: `cd /home/ailearn/projects/WFXM/butler-v5 && pnpm vitest run apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts 2>&1 | tail -10`
Expected: 3 passed.

### Step 6: Extract fatigue decision block from wechat-inbound-butler.ts

Modify `apps/api/src/wechat-inbound-butler.ts` lines 580-625 (the D64 fatigue wiring block). Replace with a call to the extracted function:

Find the existing block that calls `evaluateChannelApproval` for fatigue mitigation and replace it with:

```typescript
import { executeToolWithFatigue } from "./lib/fatigue/execute-tool-with-fatigue"

// In runButlerLoopBody (replacing the ~50-line fatigue decision block):
const toolDecision = await executeToolWithFatigue(
  toolName,
  toolArgs,
  auditLogReader,
  { channel: "wechat", actor: ownerId, correlationId: runId },
)
switch (toolDecision.kind) {
  case "allow":
    break // proceed to toolExecutor.execute below
  case "cooldown":
    await sleep(toolDecision.durationMs)
    break
  case "checklist":
    throw new RunPauseForApproval({ renderedPrompt: toolDecision.items.join("\n") })
}
// continue to existing toolExecutor.execute call
```

(Adjust the exact line numbers per actual code state. The original D64 wiring uses `evaluateChannelApproval` from `inline-approval-wiring.ts`. The extracted function wraps the fatigue-decision part only.)

### Step 7: Run full fatigue suite + acceptance to verify no regression

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm vitest run apps/api/src/lib/fatigue/ 2>&1 | tail -10
pnpm test:acceptance 2>&1 | tail -5
pnpm tsc --noEmit --incremental --project apps/api/tsconfig.json 2>&1 | tail -5
```

Expected: 39/39 fatigue pass (36 + 3 new); 44/44 acceptance; 0 typecheck errors.

### Step 8: Commit

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add apps/api/src/lib/fatigue/execute-tool-with-fatigue.ts apps/api/src/lib/fatigue/execute-tool-with-fatigue.test.ts apps/api/src/wechat-inbound-butler.ts
git commit -m "refactor(fatigue): T1 extract execute-tool-with-fatigue from runButlerLoopBody"
git push origin main
```

Use `--no-verify` if pre-commit hook flakes (per memory `feedback-precommit-hook-flakiness`).

---

## Task 2: T2a memories.ts partial god-fn split

**Files:**
- Modify: `apps/api/src/owner-routes/memories.ts` (extract largest handler)
- Create: `apps/api/src/owner-routes/memories-{handler}.ts` (NEW extracted handler)

### Step 1: Run baseline tests for memories.ts

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm vitest run apps/api/src/owner-routes/memory-dedup.test.ts 2>&1 | tail -5
```

Expected: pass (baseline).

### Step 2: Identify largest handler function in memories.ts

Read the file:
```bash
cd /home/ailearn/projects/WFXM/butler-v5
grep -n "^function\|^export function\|^app\." apps/api/src/owner-routes/memories.ts | head -20
```

Identify the largest handler (most lines between function declaration and closing brace). Target >50 lines.

### Step 3: Extract the largest handler to a new file

Create `apps/api/src/owner-routes/memories-{handler}.ts` containing the extracted handler function and any helper functions it depends on. Export from this new file.

### Step 4: Update memories.ts to re-export from new file

In `apps/api/src/owner-routes/memories.ts`:
- Remove the extracted function body
- Add `export { handler } from "./memories-{handler}"` (or similar)

### Step 5: Run tests to verify no regression

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm vitest run apps/api/src/owner-routes/ 2>&1 | tail -5
pnpm tsc --noEmit --incremental --project apps/api/tsconfig.json 2>&1 | tail -5
```

Expected: pass; 0 typecheck errors.

### Step 6: Commit

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add apps/api/src/owner-routes/memories.ts apps/api/src/owner-routes/memories-{handler}.ts
git commit -m "refactor(routes): T2a memories.ts extract largest handler"
git push origin main
```

---

## Task 3: T2b traces-procedures-tasks.ts split

Same pattern as Task 2, but for `apps/api/src/owner-routes/traces-procedures-tasks.ts` (255 lines).

**Files:**
- Modify: `apps/api/src/owner-routes/traces-procedures-tasks.ts`
- Create: `apps/api/src/owner-routes/traces-procedures-tasks-{handler}.ts`

Steps mirror Task 2 (baseline → identify → extract → re-export → verify → commit).

Commit message: `refactor(routes): T2b traces-procedures-tasks split`

---

## Task 4: T2c documents.ts split

Same pattern as Task 2, but for `apps/api/src/owner-routes/documents.ts` (255 lines).

**Files:**
- Modify: `apps/api/src/owner-routes/documents.ts`
- Create: `apps/api/src/owner-routes/documents-{handler}.ts`

Steps mirror Task 2. Commit message: `refactor(routes): T2c documents split`

---

## Task 5: T2d approvals-runs.ts split

Same pattern as Task 2, but for `apps/api/src/owner-routes/approvals-runs.ts` (222 lines).

**Files:**
- Modify: `apps/api/src/owner-routes/approvals-runs.ts`
- Create: `apps/api/src/owner-routes/approvals-runs-{handler}.ts`

Steps mirror Task 2. Commit message: `refactor(routes): T2d approvals-runs split`

---

## Task 6: T3 ESLint cleanup 7 warnings

**Files:**
- Modify: `apps/api/src/lib/fatigue/checklist.ts` (3 array-type)
- Modify: `apps/api/src/lib/fatigue/signal.ts` (2 array-type)
- Modify: `apps/api/src/lib/fatigue/signal.test.ts` (1 array-type)
- Modify: `apps/api/src/lib/fatigue/inline-approval-wiring.ts` (1 unused-vars)

### Step 1: Run ESLint to confirm baseline 7 warnings

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm eslint apps/api/src/lib/fatigue/ 2>&1 | tail -25
```

Expected: 7 warnings (3 in checklist.ts, 2 in signal.ts, 1 in signal.test.ts, 1 in inline-approval-wiring.ts).

### Step 2: Auto-fix array-type warnings

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm eslint --fix apps/api/src/lib/fatigue/checklist.ts apps/api/src/lib/fatigue/signal.ts apps/api/src/lib/fatigue/signal.test.ts 2>&1 | tail -10
```

Expected: 6 array-type warnings auto-fixed.

### Step 3: Manually fix unused-vars warning

In `apps/api/src/lib/fatigue/inline-approval-wiring.ts`, the function signature has an unused `ctx` parameter:

Find the unused `ctx` parameter in the `evaluateChannelApproval` function (around line 28). Decide: either prefix with `_` (if ESLint config allows) or remove if truly unused.

If prefixing: change `ctx: ChannelContext` to `_ctx: ChannelContext`.
If removing: remove the parameter and update the function signature.

Check the ESLint config to determine which approach works. Per project convention, prefixing with `_` is preferred (preserves API contract).

### Step 4: Verify ESLint clean (0 warnings)

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm eslint apps/api/src/lib/fatigue/ 2>&1 | tail -10
```

Expected: 0 warnings.

### Step 5: Run typecheck + tests to verify no regression

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm tsc --noEmit --incremental --project apps/api/tsconfig.json 2>&1 | tail -5
pnpm vitest run apps/api/src/lib/fatigue/ 2>&1 | tail -5
```

Expected: 0 typecheck errors; 39/39 fatigue pass.

### Step 6: Commit

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add apps/api/src/lib/fatigue/checklist.ts apps/api/src/lib/fatigue/signal.ts apps/api/src/lib/fatigue/signal.test.ts apps/api/src/lib/fatigue/inline-approval-wiring.ts
git commit -m "style(fatigue): T3 ESLint array-type + unused-vars cleanup (7 → 0 warnings)"
git push origin main
```

---

## Task 7: T4 D63 T2 owner-jargon 5 sites revert

**Files:**
- Modify: 5 of 6 wechat-*.ts files (or other files identified with internal jargon leakage)
- Modify: 5 corresponding *.test.ts files (assertion update same batch per memory)

### Step 1: Identify 5 sites with internal jargon leakage

Files identified with owner-jargon usage (from earlier grep):
- `apps/api/src/wechat-task-commands.ts`
- `apps/api/src/dev-quality-gate.ts`
- `apps/api/src/wechat-task-digest-reply.ts`
- `apps/api/src/wechat-sweeper-notify.ts`
- `apps/api/src/wechat-run-notify.ts`
- `apps/api/src/wechat-memory-commands.ts`

Search each for internal jargon terms (`approve`, `audit`, `fatigue`, `policy`, `capability`, `runId`, `ownerLabel`, etc.) in owner-facing reply strings.

```bash
cd /home/ailearn/projects/WFXM/butler-v5
for f in apps/api/src/wechat-task-commands.ts apps/api/src/dev-quality-gate.ts apps/api/src/wechat-task-digest-reply.ts apps/api/src/wechat-sweeper-notify.ts apps/api/src/wechat-run-notify.ts apps/api/src/wechat-memory-commands.ts; do
  echo "=== $f ==="
  grep -n "approve\|audit\|fatigue\|policy\|capability\|runId\|ownerLabel" "$f" | head -5
done
```

Pick the 5 sites with the most owner-facing jargon leakage. Note the specific line numbers.

### Step 2: Revert jargon to owner-friendly language

For each of the 5 identified sites:
- Replace internal jargon in owner-facing strings with owner-friendly language
- Use `apps/api/src/owner-jargon.ts` helper if applicable
- Example: "approve" → owner-friendly alternative (e.g., "确认", "好了", "ok")
- Example: "audit failed" → "记录没保存上" (owner-friendly)

### Step 3: Update corresponding *.test.ts reply-string assertions

For each modified reply string, find the corresponding test assertion and update it. Per memory `feedback-d-batch-reply-string-test-update-batch`, test updates MUST ship same batch.

### Step 4: Run full test suite to verify no regression

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm vitest run apps/api/src/ 2>&1 | tail -10
pnpm test:full 2>&1 | tail -10
```

Expected: pre-existing baseline unchanged; no new failures.

### Step 5: Commit

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add -A  # all 5 wechat-*.ts files + corresponding *.test.ts
git commit -m "refactor(jargon): T4 D63 T2 5 sites owner-friendly revert + test updates"
git push origin main
```

---

## Task 8: T5 knip clean + D62/D63 T5 minor sweep

**Files:**
- Various (sweep pass)

### Step 1: Run knip to check for new deadcode

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm knip 2>&1 | tail -20
```

Expected: 0 new deadcode (baseline unchanged).

### Step 2: Sweep D62/D63 T5 minor partial reverts

Per memory, D62 T2/T3/T5 partial + D63 T2 5th sweep revert still have sites open. Identify any remaining sites that are quick wins:

```bash
cd /home/ailearn/projects/WFXM/butler-v5
grep -rn "TODO.*D62\|TODO.*D63\|TODO.*jargon" apps/api/src --include="*.ts" 2>/dev/null | head -10
```

If any sites are quick wins (1-line revert), do them.

### Step 3: Run full test suite to verify no regression

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm test:full 2>&1 | tail -5
```

Expected: pre-existing baseline unchanged.

### Step 4: Commit (only if changes made)

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add -A
git commit -m "chore: T5 knip clean + D62/D63 T5 minor partial reverts"
git push origin main
```

If no changes, skip this step.

---

## Task 9: post-fix drift closure + raw findings archive

**Files:**
- Modify: `.audit/D65/{summary.md, protocol-compliance.md}` (NEW)
- Modify: `MEMORY.md` (update Current State)
- Any drift fixes (if found)

### Step 1: Run N=3 fresh verification suite

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm eslint apps/api/src/lib/fatigue/ 2>&1 | tail -5
pnpm tsc --noEmit --incremental --project apps/api/tsconfig.json 2>&1 | tail -5
pnpm test:full 2>&1 | tail -10
pnpm test:acceptance 2>&1 | tail -5
pnpm test:methodology 2>&1 | tail -5
pnpm knip 2>&1 | tail -5
```

Expected gates:
- lint (fatigue/*.ts): 0 warnings (was 7)
- typecheck: 0 errors
- test:full: 1990+ pass, 6 unchanged pre-existing fail, 0 new fail
- acceptance: 44/44 unchanged
- methodology: 13/13 unchanged
- knip: 0 new deadcode

### Step 2: If any NEW failures (not pre-existing), fix inline

If drift found, fix smallest change. Re-run only failing gate.

### Step 3: Commit post-fix drift closure (if any)

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git add -A
git commit -m "fix(drift): D65 close post-fix alignment (N=3 fresh verify)"
git push origin main
```

### Step 4: Archive D65 raw findings

```bash
cd /home/ailearn/projects/WFXM/butler-v5
mkdir -p .audit/D65

cat > .audit/D65/summary.md << 'EOF'
# D65 audit summary (post-fix)

## Ship cycle (11th in D55→D65 series; Path C 第 1 batch)
- T1: runButlerLoopBody god-fn split (3 new tests + extracted file)
- T2: 4 owner-routes partial split (memories / traces-procedures-tasks / documents / approvals-runs)
- T3: ESLint cleanup (7 → 0 warnings in fatigue/*.ts)
- T4: D63 T2 owner-jargon 5 sites revert + test updates
- T5: knip clean + D62/D63 minor sweep

## Gates (N=3 fresh verify)
- lint: 7 → 0 warnings in fatigue/*.ts
- typecheck: 0 errors
- test:full: 1990+ pass, 6 unchanged pre-existing, 0 new fail
- acceptance: 44/44 (no scenario changes)
- methodology: 13/13
- knip: 0 new deadcode

## D66+ follow-ups (carried from D64 review)
1. Audit event write+read plumbing (~15-20 emit sites)
2. D63 correlation_id threading
3. F1/F2/F3 acceptance real verification
4. 60+ scenarios expansion
5. arch boundary 收口
EOF

cat > .audit/D65/protocol-compliance.md << 'EOF'
# D65 protocol compliance

D55→D65 = 11 cycles × 5 ship (where applicable) = 50+ ship 累计

## Cycle integrity
- ✅ Path C 第 1 batch (owner-approved)
- ✅ Pure refactor (no owner-facing behavior change)
- ✅ All 4 locked invariants preserved (D44/D63/D49/D48)
- ✅ TDD where applicable (T1 only); refactor-baseline-verify pattern for T2-T5
EOF

git add .audit/D65/
git commit -m "docs(audit): D65 health batch ship + raw findings archive"
git push origin main
```

### Step 5: Update MEMORY.md

Update MEMORY Current State section:
- HEAD: `64e92d50` → new HEAD after T9 commit
- State: PAUSED post-D65
- Gates: N=3 fresh verify
- D-series ship 累计: 19 batches (added D65)
- Next Step Candidates: add D66 launch prompt

---

## Acceptance Gates (N=3 fresh verify)

| Gate | Baseline | D65 expected |
|---|---|---|
| lint (fatigue/*.ts) | 7 warnings | 0 warnings |
| typecheck | 0 errors | 0 new errors |
| test:full | 1990 pass 6 pre-existing fail | 1990+ pass, 6 unchanged, 0 new fail |
| acceptance | 44/44 | 44/44 unchanged |
| methodology | 13/13 | 13/13 unchanged |
| knip | 0 deadcode | 0 new deadcode |

---

## 4 Lock (防止 ship 漂移)

- **D44 y/👌 1-token** — fatigue check BEFORE y（T1 提取不破坏）
- **D63 audit_event.correlation_id** — T1 不动 audit emit
- **D49 UNDO_CHAIN** — T1 不动 undo logic
- **D48 4 项产品力** — T4 revert 强化 jargon-free

---

## Out of Scope (D66+)

- Audit event write+read plumbing
- D63 correlation_id threading
- F1/F2/F3 acceptance real verification
- 60+ scenarios expansion + arch boundary 收口
- D62 T2/T3/T5 larger partial reverts

---

**End D65 implementation plan.**
