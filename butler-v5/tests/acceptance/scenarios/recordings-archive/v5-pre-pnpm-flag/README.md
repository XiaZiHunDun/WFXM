# v5 — pre-pnpm-flag baseline (post-P2)

**Date**: 2026-09-04
**Status**: SUPERSEDED (preserved for history)

## State

- System prompt: + read_file-first guidance (`9871c417`)
- No `firstNonFlagArg` policy helper yet
- 35 scenarios recorded

## Aggregate metrics (recorded 2026-09-04)

- decision match: **26/32 = 81%** (+9pp vs v4)
- total latency: 171,498ms (-29%)
- unknown tool warnings: 0 (P2 fixed A10/C10)
- A10/C10: fixed
- D1 latency: 21.8s → 8.3s (better prompt convergence)

## What changed next

Commit `cb2c52d7 fix(domain): skip leading flags in pnpm/git read-only bypass (A9)` applied →
v6-pre-bounded-find.

## Restoration

```bash
cp -r v5-pre-pnpm-flag/*.json tests/acceptance/scenarios/recordings/
```
