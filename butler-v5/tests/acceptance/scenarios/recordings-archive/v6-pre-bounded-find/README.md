# v6 — pre-bounded-find baseline (post-A9)

**Date**: 2026-09-07
**Status**: SUPERSEDED (preserved for history)

## State

- Policy: `firstNonFlagArg` for pnpm/git (`cb2c52d7`)
- No bounded find yet, no convergence prompt yet
- 35 scenarios recorded

## Aggregate metrics (recorded 2026-09-07)

- decision match: **25/32 = 78%** (-3pp vs v5; A9 only fixed argv parsing, no behavioral change beyond A9 case)
- total latency: 151,427ms
- A9 `pnpm -r typecheck`: fixed
- D4 turn 2: still `WaitForApproval` (find)

## What changed next

Commit `7c65bbea fix(domain+prompt): bounded find bypass (-maxdepth ≤ 3) + convergence signal (D4 turn 2)` applied →
v7-current.

## Restoration

```bash
cp -r v6-pre-bounded-find/*.json tests/acceptance/scenarios/recordings/
```
