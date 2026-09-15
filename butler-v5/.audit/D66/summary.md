# D66 audit summary (post-fix)

## Ship cycle (Path C 第 2 batch — observability plumbing)
- T1a: listRecentAuditEvents read method (RuntimeStore contract + 2 impls + wrapper + 4 unit tests + cross-impl parity tests)
- T1b-apps-api: correlationId to 22 emit sites across 11 apps/api/src files
- T1b-packages-runtime: correlationId to 12 emit sites across 4 packages/runtime/src files (run-lifecycle.ts has 6 of these)
- T1c: AuditFatigueDetail thread to chokepoint (wechat-inbound-butler.ts) — new audit emit with action `fatigue.decision`

## Gates (N=3 fresh verify)
- lint: 0 unchanged
- typecheck: 0 errors (4 projects: apps/api / persistence / domain / runtime)
- test:full: 1994+ pass, 5 unchanged pre-existing fail (N=3 run-to-run: 7/6/5 — flaky eval real-LLM under load), 0 new fail
- acceptance: 44/44 unchanged (no scenario changes — observability batch is infra-only)
- methodology: 13/13 unchanged
- knip: 0 new deadcode (only pre-existing entry redundancy warnings)

## Drift closure
- tests/acceptance/scenarios/_analyze.md UUID refresh (workspace hash regeneration: wb-accept-ws-QDacEj → wb-accept-ws-8vr4qR). T1-T5 substantive content preserved. Commit: 54fd7a32 (post-fix)

## Commits (6 atomic, 5 ship + 1 post-fix)
- 4d52d0b1: feat(audit) T1a listRecentAuditEvents read method
- 714ce1c8: fix(audit) T1a correlationId optional + cross-impl parity + comment accuracy
- ff4db3b0: docs(spec) D66 §2.1 listRecentAuditEvents wrapper DI signature
- e1fa5a22: refactor(audit) T1b-apps-api correlationId to 22 emit sites
- 4bfb7fd7: refactor(audit) T1b-packages-runtime correlationId to 12 emit sites
- d8856205: feat(audit) T1c AuditFatigueDetail thread to chokepoint [MANUAL-OVERRIDE]
- 54fd7a32: fix(drift) D66 close _analyze.md baseline refresh (N=3 verify; T1+T2+T3+T4+T5 substantive content preserved)

## D67+ follow-ups (Path C continues)
1. F1/F2/F3 acceptance real verification (runtimeStore.createStep integration in fatigue checklist branch + harness audit event writes) — NOW unblocked by D66 read method
2. 60+ scenarios expansion + arch boundary 收口
3. D62 T2/T3/T5 larger partial reverts
4. `runButlerLoopBody` further god-fn splits
5. Schema migration: add dedicated `actor` column to `audit_events` (currently mapped to `subject` per D58 T1)

## Locked invariants (verified preserved)
- D44 y/👌: no inline approval changed
- D63 audit_event.correlation_id: NOW threaded (closes D63 review #2 carry)
- D49 UNDO_CHAIN: no chain logic touched
- D48 4 项产品力: no owner-facing strings changed
- Backward compat: correlationId is optional on contract; existing callers without it work unchanged
