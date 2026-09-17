# D67 — Acceptance Real Verification + Scenarios Expansion（设计文档）

> 来源：D66 cycle review + Path C 推荐 — 第 3 batch = acceptance。Owner 选 Balanced（T1 + T2a scenarios；skip arch boundary）。
>
> 范围：D67 = F1/F2/F3 acceptance real verification（runtimeStore.createStep integration + harness audit writes）+ 8 new scenarios（acceptance 44→52+）。
>
> 性质：UNBLOCKED by D66 listRecentAuditEvents（harness 读 audit data 触发真实 cooldown）。T2b arch boundary 收口 defer D68+。

---

## 1. Architecture overview

```
D67 — Path C 第 3 Batch
    │
    ├── T1a: runtimeStore.createStep at fatigue checklist branch
    │       │
    │       wechat-inbound-butler.ts:622-637 (checklist case)
    │       ↓
    │       Before throw RunPauseForApproval:
    │       call runtimeStore.createStep(...)
    │       ↓
    │       Owner "确认" finds pending step (via runtimeStore.getStep) + resume
    │
    ├── T1b: Acceptance harness audit writes
    │       │
    │       _fixtures.ts + realistic.test.ts
    │       ↓
    │       Harness scenario execution emits audit events (via existing appendAuditEvent)
    │       ↓
    │       Use D66 listRecentAuditEvents to read back + verify
    │       ↓
    │       F1 high-signal data → real cooldown (not flow smoke)
    │       F2 owner "确认" → real proceed via createStep
    │       F3 GET /fatigue returns real sequences
    │
    ├── T2a-1: 4 new C category scenarios (fatigue/cooldown/replay)
    │       │
    │       _fixtures.ts (scenariosC extension)
    │       ↓
    │       F1 real cooldown verification scenario
    │       F2 checklist proceed scenario
    │       F3 replay API real surface scenario
    │       + 1 additional C scenario
    │
    ├── T2a-2: 4 new D category scenarios (arch boundary edge cases)
    │       │
    │       _fixtures.ts (scenariosD extension)
    │       ↓
    │       Cross-channel consistency scenario
    │       Audit correlation continuity scenario
    │       Owner-direct API call (no inbound run) scenario
    │       + 1 additional D scenario
    │
    └── post-fix: drift closure + raw findings archive
```

### 关键不变量

- D44 y/👌 1-token preserved（createStep integration 在 fatigue 路径，不动 inline approval flow）
- D63 audit_event preserved（use existing listRecentAuditEvents + appendAuditEvent）
- D49 UNDO_CHAIN preserved（no chain logic touched）
- D48 4 项产品力 preserved（no owner-facing strings changed）
- D66 listRecentAuditEvents used by harness（read-side only — D66 T1a already shipped）

---

## 2. Components & Data Structures

### 2.1 T1a: runtimeStore.createStep integration

**File:** `apps/api/src/wechat-inbound-butler.ts` (lines 622-637, checklist case)

**Before:**
```typescript
case "checklist": {
  const toolName = String(def.name)
  const renderedPrompt = [
    `此操作 [${toolName}] 不可撤销，请确认：`,
    ...toolDecision.items.map((item, i) => `${i + 1}. ${item}`),
  ].join("\n")
  throw new RunPauseForApproval({
    reply: renderedPrompt,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "WaitForApproval" as ModelDecision["_tag"],
    traces: [
      `fatigue checklist ${toolName} items=${toolDecision.items.length}`,
    ],
  } satisfies ButlerLoopResult)
}
```

**After:**
```typescript
case "checklist": {
  const toolName = String(def.name)
  const renderedPrompt = [
    `此操作 [${toolName}] 不可撤销，请确认：`,
    ...toolDecision.items.map((item, i) => `${i + 1}. ${item}`),
  ].join("\n")
  // D67 T1a — persist pending step so owner "确认" can resume
  await wiring.runtimeStore.createStep({
    id: crypto.randomUUID(),
    runId: args.runId,
    kind: "approval",
    status: "waiting",
    input: {
      reason: "fatigue_checklist",
      toolName,
      items: toolDecision.items,
    },
    createdAt: new Date(),
  })
  throw new RunPauseForApproval({
    reply: renderedPrompt,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "WaitForApproval" as ModelDecision["_tag"],
    traces: [
      `fatigue checklist ${toolName} items=${toolDecision.items.length}`,
    ],
  } satisfies ButlerLoopResult)
}
```

### 2.2 T1b: Acceptance harness audit writes

**File:** `tests/acceptance/scenarios/_fixtures.ts` (existing harness support)

Harness scenarios inject audit events via `runtimeStore.appendAuditEvent` — the canonical source for `subagentAuditAsFatigueReader` (which reads via `runtimeStore.listRecentAuditEvents`). Use in scenarios that need to set up audit state (F1, F2, F3).

### 2.3 T2a: 8 new acceptance scenarios

**File:** `tests/acceptance/scenarios/_fixtures.ts` (scenariosC + scenariosD extension)

#### T2a-1: 4 new C category scenarios (C extension)

| ID | Description |
|---|---|
| `C-F1-real-cooldown` | 4 consecutive approvals → 4th triggers REAL cooldown (high-signal data injected) |
| `C-F2-checklist-proceed` | sensitive tool → checklist → owner "确认" → proceed (via createStep) |
| `C-F3-replay-api` | GET /v1/owner/audit/fatigue + POST /replay real surface (no chat-side indirection) |
| `C-additional-1` | Owner-direct API call w/o inbound run (correlation_id: null path) |

#### T2a-2: 4 new D category scenarios (D extension)

| ID | Description |
|---|---|
| `D-cross-channel-consistency` | Same scenario via wechat + telegram + CLI — verify same audit trail |
| `D-audit-correlation-continuity` | Verify correlation_id threaded across 5 consecutive emit sites |
| `D-owner-direct-no-inbound` | Owner-direct API call → correlation_id null + audit emit |
| `D-additional-2` | Failure recovery (audit_event emit failure → graceful continue) |

---

## 3. Data Flow

### T1a — createStep at checklist

```
owner sends sensitive tool request via wechat
    ↓
wechat-inbound-butler.ts executeTool
    ↓
executeToolWithFatigue(toolName, toolArgs, reader)
    ↓
returns toolDecision.kind === "checklist"
    ↓
await runtimeStore.createStep({ kind: "owner_approval", status: "pending", ... })
    ↓
throw RunPauseForApproval({ reply: renderedPrompt, ... })
    ↓
owner "确认"
    ↓
approval-resume.ts finds pending step (via runtimeStore.getStep)
    ↓
resumes approval → execute tool
```

### T1b — Harness audit writes

```
Test scenario starts
    ↓
Harness calls emitAuditEvent(store, { actor, action, subject, detail })
    ↓
store.appendAuditEvent writes to audit_events table
    ↓
Scenario execution triggers fatigue check (via subagentAuditAsFatigueReader)
    ↓
Reader now reads real audit data (not subagent log)
    ↓
F1: 4 audit events → count=4 → policy returns cooldown (REAL)
```

### T2a — Scenario execution

```
realistic.test.ts runs scenario
    ↓
Scenario fixture sets up harness state (audit emit helpers called)
    ↓
Scenario owner messages execute
    ↓
Expectations verified (minToolCalls / requireApproval / replyContains / etc.)
```

---

## 4. Error Handling

| Failure | T1a behavior | T1b/T2a behavior |
|---|---|---|
| `createStep` throws | existing try/catch in chokepoint (mirror inline approval pattern) | N/A |
| Audit emit failure | graceful continue (D58 T1 silent-failure sweep) | N/A |
| Harness setup error | test failure (correct behavior) | N/A |
| Existing scenarios break | regression caught at N=3 verify | N/A |

---

## 5. Testing

### 5.1 Unit (T1a)

**File:** `apps/api/src/wechat-inbound-butler.test.ts` (extend existing)

| Case | Description | Assertion |
|---|---|---|
| U1 | fatigue checklist triggers createStep before RunPauseForApproval | runtimeStore.createStep called with correct args |
| U2 | inline approval path unchanged (no createStep from fatigue) | existing tests pass |
| U3 | createStep with kind="owner_approval" + status="pending" | verify fields |

### 5.2 Acceptance (T1b + T2a)

**File:** `tests/acceptance/scenarios/realistic.test.ts` + `_fixtures.ts`

| Case | Description | Assertion |
|---|---|---|
| F1 (rewritten) | 4 audit events → real cooldown | 4th tool execution has actual 3s sleep + reply shows "稍等 3s..." |
| F2 (rewritten) | sensitive tool → checklist → owner "确认" → proceed | tool execution continues after ack |
| F3 (rewritten) | GET /fatigue + POST /replay real surface | non-empty sequences returned + reversible/irreversible split correct |
| New C scenarios (4) | various fatigue/cooldown/replay paths | scenario-specific assertions |
| New D scenarios (4) | cross-channel / correlation / failure recovery | scenario-specific assertions |

### 5.3 Existing — no regression

All existing 44 scenarios must pass unchanged + new 8 = 52+ total.

---

## 6. Files Changed (预估)

| Track | File | Change |
|---|---|---|
| T1a | `apps/api/src/wechat-inbound-butler.ts` | +~15 lines at checklist case |
| T1a | `apps/api/src/wechat-inbound-butler.test.ts` | +3 unit tests |
| T1b | `tests/acceptance/scenarios/_fixtures.ts` | +emitAuditEvent helper + F1/F2/F3 rewrite |
| T2a-1 | `tests/acceptance/scenarios/_fixtures.ts` | +4 C scenarios |
| T2a-2 | `tests/acceptance/scenarios/_fixtures.ts` | +4 D scenarios |
| post-fix | `.audit/D67/{summary.md, protocol-compliance.md}` | NEW |
| post-fix | `MEMORY.md` | Current State update |

预估 net: +400 lines (mostly new scenarios).

---

## 7. v5 DESIGN alignment

- §7.1 Ports: no new ports; existing RuntimeStore.createStep + appendAuditEvent + listRecentAuditEvents used
- §10.4 Sandbox: no sandbox changes
- §11.3 Approval: fatigue checklist → createStep → resume flow (extension of existing approval flow)
- §12 Knowledge: no durable memory changes
- §18 Trigger guard: owner-triggered Path C 第 3 batch launch (explicit ask)

---

## 8. Lessons / 注意事项

- **T1a createStep integration**: keep the existing RunPauseForApproval throw — createStep is the persistence step that makes the resume work
- **T1b harness audit writes**: use existing appendAuditEvent; harness reads via existing subagentAuditAsFatigueReader (which now sees real audit data, not subagent JSONL)
- **T2a scenario categories**: maintain A/B/C/D convention; 4 new C (fatigue/cooldown/replay) + 4 new D (boundary/correlation/failure)
- **Real cooldown verification**: F1 acceptance now triggers REAL 3s sleep (not flow smoke); N=3 verify may take longer
- **Harness support**: emitAuditEvent helper is the only new infrastructure; reuses existing runtimeStore

---

## 9. Acceptance Gates (N=3 fresh verify)

| Gate | Baseline | D67 expected |
|---|---|---|
| lint | 0 fatigue warnings | 0 unchanged |
| typecheck | 0 errors | 0 new |
| test:full | 1994 pass / 5 pre-existing | 1994+ pass, 5 unchanged, 0 new fail |
| acceptance | 44/44 | 52+/52+ (44 baseline + 8 new) |
| methodology | 13/13 | 13/13 unchanged |
| knip | 0 new deadcode | 0 new |

---

## 10. Out of scope (D68+)

- Arch boundary 收口
- T1c fatigue_signal coverage (extend ToolExecutionDecision)
- T1b owner-routes correlation (14 sites null → owner-identity)
- D62 T2/T3/T5 larger partial reverts
- Schema migration: dedicated `actor` column
- `runButlerLoopBody` further god-fn splits
- D60 cleanup 32+50 defer backlog

---

**End D67 design doc.**
