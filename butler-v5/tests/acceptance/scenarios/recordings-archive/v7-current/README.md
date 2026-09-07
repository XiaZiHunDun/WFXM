# v7 — current baseline (post-D4 turn 2)

**Date**: 2026-09-07
**Status**: ACTIVE

## State

- Policy: `firstNonFlagArg` + bounded find (`-maxdepth` ≤ 3) (`cb2c52d7` + `7c65bbea`)
- System prompt: + read_file-first + convergence signal (`9871c417` + `7c65bbea`)
- 35 scenarios recorded

## Aggregate metrics (recorded 2026-09-07)

- decision match: **28/32 = 88%** (+3 vs v6, +16pp vs v3 baseline)
- total latency: 178,494ms (-26% vs v3 baseline)
- unknown tool warnings: 0
- A10/C10/A9/D4(both turns): fixed
- D1 loop exhausted: clarification reply

## Comparison with previous

| Version | decision match | latency | A10/C10 | D4 t2 |
| --- | --- | --- | --- | --- |
| v3 (lost, MEMORY ref) | 72% | 240s | broken | broken |
| v4 (post-P1) | 72% | 240s | broken | broken |
| v5 (post-P2) | 81% | 171s | **fixed** | broken |
| v6 (post-A9) | 78% | 151s | fixed | broken |
| v7 (post-D4 t2) | **88%** | **178s** | fixed | **fixed** |

## Rotation policy

When next prompt/policy change is needed:

```bash
# 1. Snapshot current
cp -r v7-current v8-pre-{change-name}-fix

# 2. Apply change + re-record
pnpm tsx --env-file=.env.local scripts/acceptance/record-real-llm.ts
cp -r tests/acceptance/scenarios/recordings v8-current  # if change is good

# 3. Diff
pnpm tsx /tmp/diff-real-llm.ts

# 4. Compare vs v7 baseline — only commit if aggregate improves
```
