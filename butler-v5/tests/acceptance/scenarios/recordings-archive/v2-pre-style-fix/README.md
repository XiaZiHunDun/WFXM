# v2 — pre-style-fix baseline (post-context-fix)

**Date**: 2026-09-04
**Status**: SUPERSEDED (preserved for history)

## State

- System prompt: + B1 owner/workspace context (`1b4d615d`)
- No reply-style + take-action bias yet
- 35 scenarios recorded

## Aggregate metrics (vs fixture, recorded 2026-09-04)

- decision match: unknown (this is round 2; PRD tracking started at round 3)

## What changed next

Commit `d3b3478a feat(system-prompt): add reply-style + take-action bias` applied
→ v3-post-style-fix (lost; never backed up).

## Restoration

```bash
cp -r v2-pre-style-fix/*.json tests/acceptance/scenarios/recordings/
```
