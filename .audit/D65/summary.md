# D65 audit summary (post-fix)

## Ship cycle (Path C 第 1 batch — 11th cycle in D55-D64 audit-driven ship protocol)
- T1: runButlerLoopBody god-fn split — extract execute-tool-with-fatigue.ts (3 new tests)
- T2: 4 owner-routes partial god-fn split — memories / traces-procedures-tasks / documents / approvals-runs
- T3: ESLint 7 → 0 warnings in fatigue/*.ts (6 array-type + 1 unused-vars)
- T4: D63 T2 owner-jargon 5 sites revert + 3 test files updated same batch
- T5: knip clean + orphan cleanup (removed `formatApprovalQuestionForOwner` from D63 T2 stale code)

## Gates (N=3 fresh verify)
- lint: 7 → 0 warnings in fatigue/*.ts
- typecheck: 0 errors
- test:full: 1994 pass / 5 unchanged pre-existing fail (4 eval timeout + 1 loopMs timing) / 1 skip / 0 new fail
- acceptance: 44/44 (no scenario changes — health batch is code-only)
- methodology: 13/13 unchanged
- knip: 0 new deadcode (1 orphan removed in T5; only config-pattern hints remain, exit 0)

## Commits (9 atomic + 1 post-fix drift)
- 59e13c8b: refactor(fatigue) T1 extract execute-tool-with-fatigue
- aa5d0ebd: fix(fatigue) T1 exhaustiveness guard + remove _ctx caller propagation + JSDoc [MANUAL-OVERRIDE]
- d17d2921: refactor(routes) T2a memories.ts extract largest handler
- 646880bd: refactor(routes) T2b traces-procedures-tasks split
- 6e81f314: refactor(routes) T2c documents split
- 2ef37d85: refactor(routes) T2d approvals-runs split
- e8cc2194: style(fatigue) T3 ESLint 7 → 0 warnings
- 276602d5: refactor(jargon) T4 D63 T2 5 sites owner-friendly revert + test updates
- fa0d0ae9: chore T5 knip clean + orphan formatApprovalQuestionForOwner removal
- e44d0d1d: fix(drift) D65 close _analyze.md UUID refresh (post-fix)

## D66+ follow-ups (carried from D64 review + D65 batch gaps)
1. Audit event write+read plumbing (~15-20 emit sites, thread AuditFatigueDetail + D63 correlation_id)
2. D63 correlation_id threading to remaining ~15 emit sites
3. F1/F2/F3 acceptance real verification (runtimeStore.createStep + audit_events read method)
4. 60+ scenarios expansion + arch boundary 收口
5. `runButlerLoopBody` further god-fn splits (still large after D65 T1 extraction)
6. D62 T2/T3/T5 larger partial reverts (deferred from D63)

## Spec drift noted
- D65 spec §2.2 T2 had placeholder for largest-handler identification (resolved at impl time per-file)
- D65 spec §2.4 T4 had placeholder for 5-site selection (resolved by grep + implementer judgment)
