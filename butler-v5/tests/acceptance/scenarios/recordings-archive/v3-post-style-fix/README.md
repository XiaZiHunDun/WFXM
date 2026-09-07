# v3 — post-style-fix baseline (LOST)

**Date**: 2026-09-04
**Status**: ⚠️ DATA LOST — no snapshot preserved

## What was here

System prompt had B1 context + reply-style + take-action bias. This is
the "current" baseline used as reference for PRD
`v5-real-llm-degradation-fixes-2026-09.md` §3 (decision match 23/32 =
72%, latency 240s, unknown tool 2, A10/C10 broken, D1 stub).

## Why lost

The first 3 recordings (v1, v2, v3) preceded the "always snapshot
before change" discipline. From v4 onwards every change was preceded
by a cp to /tmp/.../recordings-pre-{change-name}-fix.

## Recovery

Re-apply context + reply-style commits to current prompt and re-record:

```bash
# From v2 (current state) + apply reply-style commit
git checkout 1b4d615d^  # pre-context state
# apply 1b4d615d + d3b3478a to current main
# ... would require a rebase, complex. Instead:
# Use v2 + manually apply the reply-style diff from d3b3478a
# then re-record. ~5 min effort.
```

Not done because round 4 metric (decision match 72% vs the round 3
baseline as captured in MEMORY.md) is the de-facto reference.

## Aggregate metrics (from MEMORY, 2026-09-04)

- decision match: 23/32 = 72%
- total latency: 240,338ms (~7,234ms/scenario avg)
- unknown tool warnings: 2
- A10/C10 approval over-trigger: broken
- D1 loop exhausted: stub
