# D67 audit summary (post-fix)

## Ship cycle (Path C 第 3 batch — acceptance real verification + scenarios expansion)
- T1a: runtimeStore.createStep at fatigue checklist (kind="approval", status="waiting", input={reason,toolName,items})
- T1b: consume-path bridge in wechat-inline-approval.ts + harness audit writes + F1/F2/F3 rewritten with real verification
- T2a-1: 4 new C category scenarios (C-F1-real-cooldown, C-F2-checklist-proceed, C-F3-replay-api, C-additional-1)
- T2a-2: 4 new D category scenarios (D-cross-channel-consistency, D-audit-correlation-continuity, D-owner-direct-no-inbound, D-additional-2)

## Gates (N=3 fresh verify)
- lint: 0 unchanged (fatigue/*.ts clean; pre-existing silentLogger prefer-const + import type in test files)
- typecheck: 0 errors
- test:full: 2015 pass, 5 unchanged pre-existing fail (4 eval/scenarios timeouts + 1 loopMs flake), 0 new fail
- acceptance: 52/52 (44 baseline + 8 new from T2a-1+T2a-2)
- methodology: 13/13 unchanged
- knip: 0 new deadcode (5 unused types + 1 unused export + 1 unused dep are pre-existing from D64/D66)

## Commits (8 atomic)
- fb89813c: feat(fatigue) T1a createStep at fatigue checklist branch [MANUAL-OVERRIDE]
- 8e656dea: docs(spec) D67 §2.1 createStep enum values (approval/waiting/crypto.randomUUID)
- e5d2c330: feat(acceptance) T1b consume-path bridge + harness audit writes + F1/F2/F3 real verification [MANUAL-OVERRIDE]
- a09445c0: feat(acceptance) T2a-1 4 new C scenarios (fatigue/cooldown/replay)
- daa8f3ff: fix(acceptance) T2a-1 C-F2-checklist-proceed use registered tool (delete_file unregistered)
- 2869e2d5: feat(acceptance) T2a-2 4 new D scenarios (arch boundary edge cases)
- 1b29f089: fix(drift) D67 close _analyze.md baseline refresh (N=3 verify)

## Issues surfaced during cycle (D67+ follow-ups)

### CRITICAL
1. **Pre-existing harness bug**: `runMultiRound` swallows errors + `realistic.test.ts` doesn't check `result.passed` (`tests/acceptance/scenarios/realistic.test.ts:202-230`). C-F2 was silently broken because of this — assertions failed but the scenario reported `passed: true`. Fix: `const result = await runMultiRound(...); expect(result.passed).toBe(true)`. **Tracking as D67+ follow-up.**

### Important
2. **D64 reader-swap follow-up still pending**: `subagentAuditAsFatigueReader` (D64 T1) reads from subagent JSONL log, not from `audit_events` table via `listRecentAuditEvents` (D66 T1a). The JSONL bridge in T1b is a workaround that triggers REAL cooldown in harness. The proper fix — swap the reader source to use `listRecentAuditEvents` — is the underlying D64 follow-up still open. **D67+ follow-up.**
3. **Spec drift: JSONL vs appendAuditEvent**: Spec §2.2 said harness uses `runtimeStore.appendAuditEvent`. Implementer used `appendAudit` (JSONL) because that's what the existing reader supports. Spec should be updated to reflect reality. **D67+ follow-up.**

### Minor
4. **Unused `ScenarioSetupCtx.app` field** added in T1b for future F3 HTTP-direct calls (currently unused). Remove or document. **D67+ follow-up.**
5. **`Scenario.followUpPatterns` field** added in T1b (pre-existing typecheck gap closure, not really new). **Resolved.**

## Locked invariants (verified preserved)
- D44 y/👌 1-token: inline approval path untouched
- D63 audit_event: now exercised by F1/F2/F3 real verification
- D49 UNDO_CHAIN: no chain logic touched
- D48 4 项产品力: owner-facing strings Chinese-first + jargon-free

## Path C completes (3 batches)
- D65 Path C 第 1 batch (god-fn + ESLint + owner-jargon) ✅
- D66 Path C 第 2 batch (observability plumbing) ✅
- D67 Path C 第 3 batch (acceptance real verification) ✅

## D68+ follow-ups (accumulated)
1. Arch boundary 收口 (T2b from D67 spec)
2. Pre-existing harness bug fix (runMultiRound error swallow + result.passed check)
3. D64 reader-swap: subagentAuditAsFatigueReader → listRecentAuditEvents
4. T1c fatigue_signal coverage (extend ToolExecutionDecision to carry signal)
5. T1b owner-routes correlation (14 owner-route sites pass null; thread owner-identity)
6. D62 T2/T3/T5 larger partial reverts
7. Schema migration: dedicated `actor` column
8. `runButlerLoopBody` further god-fn splits
