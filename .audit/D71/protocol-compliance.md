# D71 protocol compliance

D55→D70 = 16 cycles; D71 = 17th cycle (audit-driven batch)

## Cycle integrity
- ✅ 3 fresh sub-tracks (code-quality + security + spec-owner-ux) — N=3 prompt-freeze per D53a methodology
- ✅ **96 raw findings (46 must-fix / 39 defer / 11 don't-fix)** saved to `.audit/D71/{sub-track}.json` per D57 lesson #1
- ✅ Cross-track top 5 ship selected (T1-T5 ship plan; 17 sites closed across 5 tracks)
- ✅ Cycle triggered by owner 1-句 ("D71 batch" — per D65+ protocol owner-trigger)

## Subagent discipline
- ✅ 3 parallel general-purpose subagents (Agent tool dispatched in single message)
- ✅ Each agent prompt self-contained + frozen schema + specific output path
- ⚠️  One agent wrote to wrong path (`butler-v5/.audit/D71/code-quality.json` instead of `.audit/D71/`) — manually relocated to canonical path before archive. Subsequent agents used correct path.
- ✅ Each sub-track returned JSON to disk + echoed in result
- ✅ No subagent overlap (different focus areas)

## D50 fresh-verify lesson
- Pre-flight confirmed clean baseline (lint 0 / typecheck 0 / test:full 2043 pass 1 PRE-EXISTING flake / acceptance 93/93 / methodology 13/13 / knip 0) — D70 ship state still healthy.
- Each ship (T1-T5) verified fresh before commit. No last-batch-green shortcuts.

## Cycle-specific incidents (planned)
- **T1 (schema migration — dedicated `actor` column)**: closes CQ-009 + SO-001 (D71 first-class + D68 pre-scoped #5). Cross-track: code-quality + spec-owner-ux. Schema migration lives in persistence package (NOT in protected-files list); runtimeStore + memory-store + AuditEventRecord type + auditFatigueReader wiring. Pre-D71 emit sites continue to work via the `'owner'` default at the store layer — emits that thread actor are opt-in.
- **T2 (MCP HTTP/SSE SSRF + symlink path traversal)**: closes SEC-001 (D70 pre-scoped #5) + CQ-012 (MCP bypass validateNetworkAllowlist) + CQ-011 (symlink bypass in channel-outbound-media) + SEC-019. Cross-track: security + code-quality. MCP host allowlist uses literal hostname check (RFC 1918, loopback, link-local, metadata ranges); operator opt-out via `BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS=1`. Symlink bypass closed via `realpathSync` for both the literal path and the allowed roots.
- **T3 (Telegram + Slack webhook user allowlist)**: closes SEC-004 + SEC-005. New `BUTLER_V5_TELEGRAM_USER_ID_ALLOWLIST` + `BUTLER_V5_SLACK_USER_ID_ALLOWLIST` env vars. Unset/empty preserves pre-D71 behavior. SEC-003 (WS subscribe caller binding) deferred — per-caller identity requires bearer auth.
- **T4 (HTTP security headers + audit JSONL umask + owner-route 429 Chinese)**: closes SEC-006 (D70 pre-scoped #7) + SEC-007 + SO-005. Headers middleware sets 6 standard headers + strips `server`/`x-powered-by`. Umask 0o077 in audit-log.ts. owner-route 429 → owner-jargon Chinese.
- **T5 (spec/scenario cleanup)**: closes SO-003 (D70 partial closure complete — 9 vacuous verify callbacks removed) + SO-002 (D67 F3 spec clarification) + SO-004 (D-additional-2 comment refresh).

## Raw findings archived
- Per D57 lesson #1: D71 raw findings archived to `.audit/D71/{code-quality,security,spec-owner-ux}.json` (3 files)
- summary.md + protocol-compliance.md (this file) — same structure as D55-D70 for downstream reference
- Code-quality.json was initially written to butler-v5/.audit/D71/ (wrong path) by one agent; manually relocated to canonical path before archive.

## Cross-cycle continuity
- D55→D70 audit-driven batches (16 cycles × 5 ship = 80 ship)
- D71 = 17th audit-driven cycle (+5 ship = 85 ship 累計)
- All cycles ship via atomic commits per D-series protocol

## Files modified this cycle (17 unique)
- packages/persistence/src/migrations/0014_audit_actor_column.sql (T1, NEW)
- packages/persistence/src/migrations/run-migrations.ts (T1)
- packages/persistence/src/schema.ts (T1)
- packages/persistence/src/runtime-store.ts (T1)
- packages/persistence/src/memory/runtime-store.ts (T1)
- packages/domain/src/runtime/store-contract.ts (T1)
- apps/api/src/lib/fatigue/audit-reader.ts (T1)
- apps/api/src/mcp-config.ts (T2)
- apps/api/src/channel-outbound-media.ts (T2)
- apps/api/src/routes.ts (T3)
- apps/api/src/index.ts (T4)
- apps/api/src/audit-log.ts (T4)
- apps/api/src/owner-routes.ts (T4)
- tests/acceptance/scenarios/_fixtures.ts (T5)
- docs/superpowers/specs/2026-09-16-d67-acceptance-design.md (T5)
- knip.json (not modified — no new deadcode)
- (2 files: butler-v5/.audit/D71/code-quality.json + D71 summary/protocol/manual artifact relocation)

## Commits (5 atomic ship)
- `9b99558a`: T1 actor column migration
- `2d40bfe1`: T2 MCP SSRF + symlink path traversal
- `8ac13994`: T3 Telegram/Slack user allowlist
- `bd761299`: T4 HTTP headers + umask + 429 Chinese
- `1c16d7d7`: T5 spec + scenario cleanup