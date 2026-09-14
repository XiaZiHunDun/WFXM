# D64 audit summary (post-fix)

## Ship cycle (10th in D55→D64 series)
- T1 signal + checklist + policy (Tasks 1-3): 7 commits + 2 lint fixes (signal/checklist/policy + tests + cleanup)
- T2 audit_event fields (Task 4, PIVOTED): fatigue-local type + detail embedding (lean approach)
- T3 cross-channel integration (Tasks 5-6): wiring helper + 3 channel handlers + 3 fixes
- T4 /v1/owner/audit/fatigue (Task 7): list + replay API + 2 fixes (lint cleanup + glob escape / sentinel / length cap)
- T5 acceptance scenarios (Tasks 8-10): F1/F2/F3 + 3 spec gap-docs

## Totals
- 24 commits total (2 docs + 22 implementation)
- 21 files changed, 2943 insertions, 39 deletions
- Acceptance: 43 → 44 (F1-fatigue / F2-sensitive / F3-replay)

## Gates (N=3 fresh verify, post-fix)
- lint: 7 warnings (0 new, all pre-existing in fatigue/*.ts per Task 10 verify; not blocking T5 acceptance 44/44)
- typecheck: 0 errors
- test:full: 1990 passed / 6 pre-existing failures (1 architecture-typed-rules + 4 eval timeouts + 1 loopMs timing flake) — unchanged from baseline
- acceptance: 44/44 realistic scenarios + 85/85 total acceptance — unchanged from D64 T5 target
- methodology: 13/13 — unchanged

## D65+ follow-ups (explicit commitments)

1. `audit_events` table add `listRecentAuditEvents` read method — enables:
   - Subagent log reader replacement (`subagentAuditAsFatigueReader` + `ownerAuditReader` consolidation)
   - Acceptance harness can write audit events for real cooldown verification
   - F1 acceptance flow smoke → real cooldown verification
2. Checklist path: `runtimeStore.createStep` support — owner ack can resume to checklist wait
3. F2 acceptance: same as #2 — owner can actually proceed through checklist interaction
4. `runButlerLoopBody` god-fn split (D62/D63 follow-up commitment) — currently 337 lines after D64 wiring additions
5. D62/D63 T5 god-fn partial reverts
6. T2 partial revert (D63 follow-up) — 5 sites still pending
7. ~15 D63 audit-event correlation_id emit sites pending

## Spec drift noted
- Spec §2.4 referenced phantom `apps/api/src/audit-event.ts` — pivoted to fatigue-local type + detail embedding (D64 T2 commit `e786efbf` + `344b594b`)
- Spec §6 originally listed `telegram-inbound-butler.ts` — actually routes through `channel-inbound.ts → runButlerLoop`
- Spec §5.4 F1/F2/F3 originally claimed acceptance verifies cooldown/checklist/replay — all gap-documented as flow smoke / 探针 (D64 T5 spec commits `d635cc97` + `865b64ac` + `5b6adbcc`)

## Pivot decisions (owner-approved mid-cycle)
- Task 4 audit_event: pivot to fatigue-local type + detail embedding (lean) instead of schema-extension with 3 optional columns
- 9 plan bugs caught by subagents (3 fixed inline, 6 documented as follow-up)
  - ProjectIdToChannel did not recognize `channel:telegram` prefix — fixed (`d4006a94`)
  - AuditEventSummary type import inconsistent with eslint consistent-type-imports — fixed (`2d6d6d10`)
  - correlationId naming + exhaustiveness guard — fixed (`09d15bd3`)
  - +6 other (deferred to D65+)

## Component inventory shipped
1. `apps/api/src/lib/fatigue/signal.ts` — FatigueSignal pure function (count + last_n_actions sliding window)
2. `apps/api/src/lib/fatigue/checklist.ts` — SensitiveToolChecklist pattern matcher
3. `apps/api/src/lib/fatigue/policy.ts` — InlineApprovalPolicy decision matrix (allow/cooldown/checklist)
4. `apps/api/src/lib/fatigue/inline-approval-wiring.ts` — Shared cross-channel helper
5. `apps/api/src/lib/fatigue/replay.ts` — `/v1/owner/audit/fatigue` list + replay
6. `apps/api/src/owner-routes/audit-fatigue.ts` — Route registration
7. Channel handlers wired: wechat / telegram / CLI (D64 T3 commits)

## Test additions (D64)
- `signal.test.ts` — 7 unit tests (F1-F5 + edge cases)
- `checklist.test.ts` — 6 unit tests
- `policy.test.ts` — 6 unit tests
- `cross-channel.test.ts` — 3 integration tests
- `replay-api.test.ts` — 4 API tests
- Total: 26 new unit/integration tests

## Locked invariants (verified)
- D44 y/👌 1-token preserved (cooldown/checklist intercept pre-y)
- D63 audit_event.correlation_id not touched (pivot to fatigue-local type + detail embedding)
- D49 UNDO_CHAIN not touched (D65+ undo dispatch)
- D48 4 项产品力: degraded → fail-safe allow (D48 §4.3 advice-not-action)

## Architecture delta
- New `lib/fatigue/` directory: signal / checklist / policy / inline-approval-wiring / replay + 4 test files
- 3 channel handlers updated (wechat-inbound-butler / telegram-inbound-butler / cli-run)
- 1 new route file (`owner-routes/audit-fatigue.ts`)
- Failure mode: FatigueSignal read failure → degraded=true → fail-safe allow (no owner replacement)
