# Real LLM Recording Baseline Archive

Per-version snapshots of `pnpm tsx scripts/acceptance/record-real-llm.ts`
output (35 scenarios × real LLM latency + tool calls + decisions).

## Layout

Each `v{N}-*` subdir contains 35 `{A,B,C,D}{1..N}.json` files (one per
scenario) + `_summary.md`. The `*.json` files are **gitignored** (real
LLM output + apiKeyMask); the `README.md` per subdir IS tracked as the
index.

| Version | Source | What changed | Date |
| --- | --- | --- | --- |
| v1-pre-context-fix | first recording | basic prompt, no context yet | 2026-09-04 |
| v2-pre-style-fix | before style commit | context injected, no reply-style yet | 2026-09-04 |
| v3-post-style-fix | (lost — never backed up) | context + reply-style baseline | 2026-09-04 |
| v4-pre-read-file-first | before P2 fix | + P1 loop-exhausted clarification | 2026-09-04 |
| v5-pre-pnpm-flag | before A9 | + read_file-first prompt | 2026-09-04 |
| v6-pre-bounded-find | before D4 turn 2 fix | + firstNonFlagArg for pnpm/git | 2026-09-07 |
| v7-current | current `recordings/` | + bounded find (-maxdepth ≤ 3) + convergence prompt | 2026-09-07 |

## Why per-version

- **Reproducible diff**: `diff -r v5 v7` shows aggregate drift case-by-case
- **Rollback target**: if a future change regresses, restore previous version
- **Audit trail**: every prompt/policy change links to a before-snapshot

## Rotation policy

When changing system prompt or `isReadOnlyCommand`:

1. `cp -r v7-current v{N+1}-pre-{change-name}-fix` (snapshot the current state)
2. Apply change + re-record → becomes v{N+2}-current
3. Run `pnpm diff:real-llm` to compare (add `-- --dir <version-subdir>` to
   diff an archived snapshot instead of the live `recordings/`)
4. If aggregate metrics improve → commit + update PRD; if regress → revert

## Disk footprint

~152KB per version × 7 versions = ~1.06 MB total. All gitignored.
No remote backup mechanism — accept loss on sandbox restart; the
RECORDING PROCESS is cheap (4 minutes for 35 scenarios) so re-recording
6 rounds of history is feasible if needed (~24 min total).

## v3-post-style-fix gap

This version is **lost** — the first 3 recordings (round 1, 2, 3)
preceded the "always backup before change" discipline. Subsequent
rounds (v4+) are all preserved. The round 3 data was equivalent to the
post-style-fix state and is recoverable via `re-recording from v2 + apply
style-fix`, but not done because the round 4 metric (decision match 72%
vs round 3 baseline) was already captured in MEMORY.md.

## Gitignore rule

```gitignore
butler-v5/tests/acceptance/scenarios/recordings-archive/*/!README.md
```

This ignores `*.json` and other contents inside each subdir but
preserves `README.md` per subdir for index survival across sandboxes.
