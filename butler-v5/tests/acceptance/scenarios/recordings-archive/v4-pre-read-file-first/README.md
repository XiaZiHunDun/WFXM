# v4 — pre-read-file-first baseline (post-P1)

**Date**: 2026-09-04
**Status**: SUPERSEDED (preserved for history)

## State

- System prompt: B1 + reply-style + take-action + P1 loop-exhausted clarification (`eb49a443`)
- No read_file-first guidance yet
- 35 scenarios recorded

## Aggregate metrics (recorded 2026-09-04)

- decision match: **23/32 = 72%** (v3-equivalent; P1 was loop-exhaust path, didn't change decision distribution)
- total latency: 240,338ms
- unknown tool warnings: 2 (A10 round 4 invented WaitForApproval/Respond)
- A10/C10 approval over-trigger: broken

## What changed next

Commit `9871c417 feat(system-prompt): read_file-first guidance` applied →
v5-pre-pnpm-flag.

## Restoration

```bash
cp -r v4-pre-read-file-first/*.json tests/acceptance/scenarios/recordings/
```
