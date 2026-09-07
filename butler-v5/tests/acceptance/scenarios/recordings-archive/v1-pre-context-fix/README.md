# v1 — pre-context-fix baseline

**Date**: 2026-09-04
**Status**: SUPERSEDED (preserved for history)

## State

- System prompt: basic, no owner/workspace context injection
- 35 scenarios recorded with `MiniMax-M3[1m]`
- Aggregate metrics unknown (this is the original baseline before PRD tracking)

## What changed next

Commit `1b4d615d feat(system-prompt): inject v5 owner + workspace context (close B1 gap)`
applied → v2-pre-style-fix was the post-context-fix state.

## Restoration

```bash
cp -r v1-pre-context-fix/*.json tests/acceptance/scenarios/recordings/
pnpm tsx /tmp/diff-real-llm.ts  # to compare vs fixture
```
