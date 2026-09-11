# D53b — TODO / FIXME Inventory (2026-09-11)

**Date:** 2026-09-11
**Scope:** butler-v5/ (all `.ts` and `.md`, excluding `node_modules` / `dist` / `_archive` / `coverage` / `tools`)
**Total raw matches:** 35 lines across 4 files
**Post-D53b state:** After 87 dead code deletions (D53a-3f)

## Summary

**Outcome: No real code TODOs exist in the v5 codebase.**

This is a healthy state — all 35 raw matches resolve to either:
1. The D53 planning/spec docs themselves (referencing TODO inventory as a deliverable)
2. False positive matches in string literals (tools.ts example, TODOIST_API_TOKEN env var name)

No deletion candidates. No D53c deferral candidates. D-series ship discipline has kept the codebase free of orphaned TODO markers.

## Classification summary

| Category | Count | Action |
|---|---|---|
| Active (D# referenced) | 0 | N/A — no code TODOs reference D# batches |
| Stale (no D# ref, no recent activity > 30d) | 0 | N/A — no stale TODOs |
| Infrastructure (planning docs, cutover scripts) | 34 | Keep — intentional references in D53a/D53b plans + D53 design spec |
| False positive (regex matched in string/comment, not a real TODO) | 1 | Keep (no action) — string literal in tool description |
| **Total** | **35** | All classified |

## Active TODOs (D# tracked)

| File | Line | Marker | D# tracking | Status |
|---|---|---|---|---|
| _(none)_ | — | — | — | — |

**Result:** Zero active TODOs in production code. All D#-tracked work resolves through commit messages and batch notes, not in-code TODO markers.

## Stale TODOs (candidate for delete or D53c deferral)

| File | Line | Marker | Last modified | Recommended action |
|---|---|---|---|---|
| _(none)_ | — | — | — | — |

**Result:** Zero stale TODOs. The 30-day staleness threshold is not applicable — there is nothing to evaluate.

## Infrastructure TODOs (kept)

All infrastructure matches are in planning/spec documents for D53 itself. These are intentional references describing the TODO inventory task as a deliverable, not orphaned TODO markers.

| File | Line | Marker | Why kept |
|---|---|---|---|
| `docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` | 64 | `TODO` | Design spec for D53 — references `todo-inventory.md` as a deliverable |
| `docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` | 186 | `TODO` | Design spec for D53 — describes grep command for TODO classification |
| `docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` | 313 | `TODO` | Design spec for D53 — TODO 分类 (classification) in deliverable table |
| `docs/superpowers/plans/2026-09-10-d53a-methodology.md` | 1162 | `TODO` | D53a plan — Placeholder scan confirmation line (negative result) |
| `docs/superpowers/plans/2026-09-11-d53b-code-health.md` | 5, 11, 38, 526, 531, 536, 559, 563, 572, 574, 578, 581, 585, 588, 592, 597, 602, 604, 607, 612, 619, 620, 772, 783, 794, 803, 837, 879, 912, 919 | `TODO` | D53b plan — Task 6 specification + template (this document is the output) |

**Total:** 34 infrastructure lines across 3 planning/spec files.

All of these are part of the D53 meta-audit spec/plans themselves and reference the TODO inventory as a deliverable. They are not actionable TODOs and should remain.

## False positives (regex noise)

| File | Line | Match context | Why false positive |
|---|---|---|---|
| `apps/api/src/tools.ts` | 498 | `'Run a short allowlisted command in the workspace (no shell). Pass `argv` as a string array, e.g. ["ls", "-la"], ["python3", "-c", "print(1)"], or ["rg", "TODO", "src"]. ...'` | String literal inside tool description — `["rg", "TODO", "src"]` is an example of using ripgrep to find TODO markers in source code, not a TODO marker itself. |

**Total:** 1 false positive.

## Wider scope (out-of-scope file types)

For completeness, the grep also matched in non-`.ts`/`.md` files. These are out of scope for this inventory but documented for transparency:

| File | Line | Match context | Why out of scope / false positive |
|---|---|---|---|
| `scripts/cutover/enable-mcp-prod.sh` | 4 | `# TODOIST_API_TOKEN, API_HEADERS in env separately.` | Comment listing env var names — `TODOIST_API_TOKEN` is an actual env var name (Todoist integration), not a TODO marker |
| `scripts/cutover/smoke-mcp-hardened.mjs` | 199 | `` `smoke ok [grant]: grant issued; MCP exec external error (check TODOIST_API_TOKEN): ${reason.slice(0, 160)}` `` | Error message text — same env var name `TODOIST_API_TOKEN` |
| `tests/acceptance/scenarios/recordings-archive/v2-pre-style-fix/B1.json` | 9 | `"... 列出今天还能落地的 TODO 清单？告诉我优先级，我开 dev 会话动手。"` | Archived recording body text (gitignored per D45 engineering-hygiene) — natural language mention of "TODO list" in a recorded assistant reply, not a code marker |
| `tests/acceptance/scenarios/recordings-archive/v2-pre-style-fix/B10.json` | 9 | `"... 里的 README、ROADMAP、TODO 文件,推断下周该推进什么吗?..."` | Same: archived recording body text mentioning "TODO file" as a category, not a code marker |

**Total:** 4 additional matches in `.sh`/`.mjs`/`.json` files — all false positives or gitignored archived content.

## Action items for D53b

**None.** This is a "report only" outcome with zero deletions.

- No stale TODOs to delete (none exist)
- No D53c deferral candidates (nothing borderline)
- No new TODOs introduced by D53b's 87 dead code deletions

## Notes for D53c / D54

- **Baseline locked:** As of 2026-09-11, the v5 codebase has zero TODO/FIXME/XXX/HACK markers in production code. This is a high bar — preserve it.
- **New TODOs policy:** If a future ship batch introduces a TODO marker (in `.ts` or `.md` excluding this planning folder), document it in this file with a D# tracking column entry. Future audits can re-run the same grep and compare.
- **D53c scope:** D53c may consider adding a `pnpm todo:check` script that re-runs this grep and fails CI if any new TODO appears in production code (excluding `docs/superpowers/` planning folder).
- **D54 hygiene batch:** If TODOs accumulate faster than they're resolved (suggesting D# tracking gap), consider a D54 "TODO hygiene" batch. Not needed now — current count is 0.

## Reproducibility

This inventory was generated with:

```bash
cd /home/ailearn/projects/WFXM/butler-v5
grep -rn "TODO\|FIXME\|XXX\|HACK" --include="*.ts" --include="*.md" \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=_archive \
  --exclude-dir=coverage --exclude-dir=tools \
  > /tmp/todo-raw-2026-09-11.txt 2>&1 || true
wc -l /tmp/todo-raw-2026-09-11.txt
# Output: 35
```

To re-verify after future batches, run the same command and compare the output. Any new matches in `.ts` files or non-planning `.md` files should trigger an update to this inventory.
