# D53b — Code Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship code health baseline (knip deadcode + vitest coverage + 0 lint/typecheck drift + TODO classification) + 修 subagent-multiturn flake (D53a route 来的), 锁住 v5 卫生基线供 D53c/D54+ 引用。

**Architecture:**
- 1 deadcode audit (knip) 替换 ts-prune (D45 教训 784 行假阳)
- 1 coverage baseline (vitest --coverage → JSON)
- 1 lint-typecheck 0-drift confirm
- 1 TODO inventory (active / stale / infrastructure 分类)
- N true dead code 删除 commit
- 1 subagent-multiturn flake fix (D53a route 来的, D50 BUTLER_V5_WECHAT_SESSION_STATE env isolation 模式)
- 1 fix-memory + MEMORY index

**Tech Stack:** TypeScript + Vitest + knip + pnpm + node:fs/path。knip 是新 dep。

**Spec:** `butler-v5/docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` §3.2

**WFXM 协议提醒:**
- Push-to-main: feature → main 直接 push（`feedback-wfxm-push-to-main`）
- Pre-commit hook: new commit 用 `--no-verify` 防误报; amend 用 probe + `--no-verify`
- Bash backtick: commit message 用 single quote
- Doc-batch pattern: 4 audit docs 1 commit, true dead per-file commit, fix-memory + index 1 commit
- D53a protocol: D53b ship claim 必须本 ship fresh verify, 不可复用 D53a output

---

## File Structure

| 类型 | 路径 | 责任 |
|---|---|---|
| 改 | `butler-v5/package.json` | +knip devDep + `deadcode:knip` script |
| 新 | `butler-v5/knip.json` (or `knip.config.ts`) | knip config (include 6 packages, exclude test fixtures) |
| 新 | `butler-v5/tools/deadcode-report.md` | knip 结果分类 (true dead / false positive / fixture / cross-pkg re-export) |
| 新 | `butler-v5/tools/coverage-baseline.json` | vitest --coverage 全量结果 (per package + low coverage modules) |
| 新 | `butler-v5/tools/lint-typecheck-report.md` | 0-drift confirm (lint / typecheck / arch-proxy) |
| 新 | `butler-v5/tools/todo-inventory.md` | TODO / FIXME / XXX / HACK 分类 |
| 改 | `butler-v5/tests/acceptance/subagent-multiturn.test.ts` | D50 env isolation pattern 修 flake |
| 多 commit | (true dead code 删除) | per file / per package 1 commit |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53b-code-health-2026-09-11.md` | fix-memory |
| 改 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` | +1 索引行 |

**设计原则:**
- `tools/` 是新 dir, 放 audit 产物, 不放 source code
- knip config 必须 exclude test fixtures (D45 教训: ts-prune 把 fixtures 当 dead code 报 784 行假阳)
- True dead 删除前必须 sample review ≥5 case, 防止 R2 (knip 误报) 风险
- 删完每个文件后 N=3 跑 acceptance (防 R3 latent import 触发)
- subagent-multiturn fix 用 D50 已 ship 模式 (`BUTLER_V5_WECHAT_SESSION_STATE` + `mkdtempSync` tmp file per test)

---

## Task 1: Install knip + add pnpm script

**Files:**
- Modify: `butler-v5/package.json`

- [ ] **Step 1: Install knip as devDep**

Run: `cd butler-v5 && pnpm add -D knip`
Expected: knip added to devDependencies, package.json updated, pnpm-lock.yaml updated

- [ ] **Step 2: Verify knip installed**

Run: `cd butler-v5 && pnpm exec knip --version`
Expected: knip version printed (e.g. `5.x.x`)

- [ ] **Step 3: Add `deadcode:knip` script to package.json**

In `butler-v5/package.json`, find the `scripts` block and add after the existing `deadcode` script (around line 48):

```json
"deadcode:knip": "knip --reporter markdown",
```

The existing `deadcode` script uses ts-prune (per D45, has 784 false positives). The new `deadcode:knip` uses knip which correctly tracks cross-package re-exports.

- [ ] **Step 4: Create knip config**

Create `butler-v5/knip.json`:

```json
{
  "$schema": "https://unpkg.com/knip@5/schema.json",
  "workspaces": {
    ".": {
      "entry": [
        "scripts/acceptance/record-real-llm.ts",
        "scripts/acceptance/diff-real-llm.ts",
        "scripts/acceptance/generate-d53a-baseline.ts"
      ]
    },
    "apps/api": {
      "entry": ["src/index.ts", "src/cli.ts"]
    },
    "apps/cli": {
      "entry": ["src/index.ts"]
    },
    "packages/adapters": {
      "entry": ["src/index.ts"]
    },
    "packages/domain": {
      "entry": ["src/index.ts"]
    },
    "packages/persistence": {
      "entry": ["src/index.ts"]
    },
    "packages/ports": {
      "entry": ["src/index.ts"]
    },
    "packages/runtime": {
      "entry": ["src/index.ts"]
    }
  },
  "ignore": [
    "**/*.test.ts",
    "**/*.test-d.ts",
    "**/_fixtures/**",
    "**/_archive/**",
    "**/node_modules/**",
    "**/dist/**",
    "tools/**",
    "docs/**",
    "**/_meta/**",
    "**/recordings/**"
  ],
  "ignoreDependencies": [
    "turbo",
    "pnpm"
  ]
}
```

**Note:** Adjust entries based on actual entry points. Run `pnpm exec knip --include-entry-exports` first to see what knip discovers, then refine this config.

- [ ] **Step 5: Test knip runs without crashing**

Run: `cd butler-v5 && pnpm deadcode:knip 2>&1 | head -30`
Expected: knip output (may show unused files/exports — that's the scan, not a crash)

If knip errors out, check the config and adjust. If it succeeds but shows many results, that's expected — Task 2 will classify them.

- [ ] **Step 6: Commit knip install + config**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/package.json butler-v5/pnpm-lock.yaml butler-v5/knip.json
git commit --no-verify -m 'chore(deadcode): D53b add knip (replaces ts-prune 784 行假阳) + knip.json config'
```

---

## Task 2: Run knip + generate deadcode-report.md

**Files:**
- Create: `butler-v5/tools/deadcode-report.md`

- [ ] **Step 1: Run knip and save raw output**

Run: `cd butler-v5 && pnpm deadcode:knip > /tmp/knip-raw-2026-09-11.md 2>&1 || true`
Expected: file at /tmp/knip-raw-2026-09-11.md with knip markdown output (knip exits non-zero when issues found, hence `|| true`)

- [ ] **Step 2: Inspect the raw output**

Run: `wc -l /tmp/knip-raw-2026-09-11.md && head -50 /tmp/knip-raw-2026-09-11.md`
Expected: dozens to hundreds of lines; sections for "Unused files", "Unused exports", "Unused dependencies", etc.

- [ ] **Step 3: Sample review ≥5 true dead candidates**

The raw output is unverified — knip may report false positives (especially for cross-package re-exports, dynamic imports, test fixtures). For at least 5 different "Unused files" or "Unused exports" entries:

For each candidate, run:
```bash
cd butler-v5
# Check if the file/export is referenced anywhere
grep -rn "<filename>" --include="*.ts" .
grep -rn "<exportName>" --include="*.ts" .
# Check if it's a cross-package re-export (false positive)
grep -rn "from.*<filename>" --include="*.ts" .
```

If grep finds references that knip missed, the entry is a **false positive** (likely cross-pkg re-export or test fixture).

- [ ] **Step 4: Classify all entries into 4 buckets**

Categorize each knip finding into one of:
- **true dead** (no references found): candidate for deletion
- **false positive** (grep finds references knip missed): keep, mark in report
- **fixture** (in _fixtures/, recordings/, scripts/): keep, knip config should have ignored but verify
- **cross-pkg re-export** (referenced by another package): keep, knip config issue

Note: knip should already be configured (Task 1) to ignore fixtures. The classification here is for entries that survived the config filter.

- [ ] **Step 5: Write tools/deadcode-report.md**

Create the file with this structure (adapt counts based on actual results):

```markdown
# D53b — Deadcode Report (knip @ 2026-09-11)

**Tool:** knip v5.x (replaces ts-prune per D45 lesson — 784 false positive in earlier scan)
**Config:** `butler-v5/knip.json`
**Raw output:** `/tmp/knip-raw-2026-09-11.md` (gitignored)
**Knip exit code:** <N> (non-zero = issues found, expected)

## Summary

| Category | Count | Action |
|---|---|---|
| Total knip findings | <N> | — |
| True dead (no references) | <N> | Delete in Task 3 |
| False positive (knip missed refs) | <N> | Keep, mark |
| Fixture (test fixture, knip should have ignored) | <N> | Keep, fix knip config |
| Cross-package re-export (referenced by another pkg) | <N> | Keep, mark |
| Infrastructure (build script, entry, etc) | <N> | Keep |

## True Dead Candidates (for Task 3 deletion)

| File / Export | Path | Verification grep |
|---|---|---|
| `<name>` | `<path>` | `grep -rn "<name>" butler-v5 --include="*.ts"` → 0 results |
| ... | ... | ... |

## False Positives (kept)

| File / Export | Path | Why false positive |
|---|---|---|
| `<name>` | `<path>` | Referenced by `<other-file>` (knip config gap) |
| ... | ... | ... |

## Fixture (kept)

| File | Path | Why kept |
|---|---|---|
| ... | ... | ... |

## Cross-package re-export (kept)

| File / Export | Path | Referenced by |
|---|---|---|
| ... | ... | ... |

## Sample Review Trail

Reviewed 5+ candidates manually (D45 lesson: ts-prune had 784 false positives, must sample before bulk delete):

1. `<file1>` → grep result: 0 refs → **true dead** → delete
2. `<file2>` → grep result: referenced by `<other>` → **false positive** → keep
3. ...

## Knip Config Issues (for D53c or D54)

If many entries are false positives due to config gaps, file issues here:

- `<config issue 1>`
- ...
```

- [ ] **Step 6: Commit deadcode report**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tools/deadcode-report.md
git commit --no-verify -m 'docs(audit): D53b deadcode report (knip scan, 4-bucket classification, sample review trail)'
```

---

## Task 3: Delete true dead code (per file / per package)

**Files:** Variable — each true dead item from Task 2

- [ ] **Step 1: List true dead files to delete**

From the deadcode-report.md "True Dead Candidates" table, get the list. If 0 true dead, skip to Task 4. Otherwise continue.

- [ ] **Step 2: For each true dead file: pre-delete verification**

For each file in the list:
```bash
cd butler-v5
# Final grep — must show 0 references (other than the file itself and its test)
grep -rn "<file-basename>" --include="*.ts" . | grep -v "<file-path>"
# Expected: 0 lines (or only test files referencing it)
```

If grep finds unexpected references, reclassify as false positive and update deadcode-report.md.

- [ ] **Step 3: For each true dead file: delete + N=3 verify**

For each file:
```bash
cd butler-v5
# Delete the file
rm <file-path>
# Run N=3 acceptance to catch any latent import
pnpm vitest run tests/acceptance 2>&1 | tail -10
# Expected: 41/41 pass, no new failures
```

If N=3 fails after deletion:
- The file was NOT actually dead (latent import or dynamic reference)
- Restore the file: `git checkout <file-path>`
- Update deadcode-report.md: reclassify as false positive
- Skip this file in this batch

- [ ] **Step 4: Commit deletions (1 commit per file or batched per package)**

For each successful deletion:
```bash
cd /home/ailearn/projects/WFXM
git add -A
git commit --no-verify -m 'chore(deadcode): D53b delete <file-basename> (knip true dead, N=3 verified)'
```

Or batched per package (e.g., all dead code in packages/domain/ in 1 commit):
```bash
git commit --no-verify -m 'chore(deadcode): D53b delete N files in packages/domain (knip true dead, N=3 verified)'
```

If you batch, the message must list the count and which files (or use `git show --stat HEAD` post-commit to verify).

- [ ] **Step 5: Re-run knip to confirm 0 true dead**

Run: `cd butler-v5 && pnpm deadcode:knip > /tmp/knip-post-deletion.md 2>&1 || true && diff /tmp/knip-raw-2026-09-11.md /tmp/knip-post-deletion.md | head -30`
Expected: The "True Dead Candidates" section is empty in post-deletion output

If true dead still present, return to Step 2 for those entries.

- [ ] **Step 6: Update deadcode-report.md with post-deletion status**

Edit `butler-v5/tools/deadcode-report.md` to add a "Post-deletion verification" section:

```markdown
## Post-deletion verification (Task 3)

Re-ran knip after deletion:
- Total findings: <N> (was <N>)
- True dead: 0 (was <N>)
- False positive: <N> (unchanged or fixed)
- Files deleted: <list with commit SHAs>
- N=3 acceptance: 41/41 (no regressions)
```

- [ ] **Step 7: Commit post-deletion report update**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tools/deadcode-report.md
git commit --no-verify -m 'docs(audit): D53b deadcode report post-deletion (true dead = 0, N=3 verified)'
```

---

## Task 4: Run vitest --coverage + generate coverage-baseline.json

**Files:**
- Create: `butler-v5/tools/coverage-baseline.json`

- [ ] **Step 1: Check current coverage config**

Run: `grep -A 20 'coverage' butler-v5/vitest.config.ts | head -30`
Expected: existing coverage config (provider, reporter, include, exclude)

- [ ] **Step 2: Run vitest coverage (full suite)**

Run: `cd butler-v5 && pnpm test:coverage 2>&1 | tail -50`
Expected: coverage summary printed + coverage/ dir generated with HTML/JSON/LCOV reports

- [ ] **Step 3: Locate coverage JSON output**

Run: `ls butler-v5/coverage/ && find butler-v5/coverage -name '*.json' | head -5`
Expected: coverage-summary.json or coverage-final.json somewhere in coverage/

- [ ] **Step 4: Parse coverage into per-package baseline format**

Write a small parser script `butler-v5/tools/parse-coverage.mjs` (one-shot, not committed to scripts/):

```javascript
import { readFileSync, writeFileSync } from "node:fs";

const summary = JSON.parse(readFileSync("coverage/coverage-summary.json", "utf8"));
const baseline = {
  snapshotDate: "2026-09-11",
  shipEvent: "D53b",
  total: summary.total,
  // per-file detail, optionally grouped by package
  files: {},
};
for (const [file, data] of Object.entries(summary)) {
  if (file === "total") continue;
  // Extract package from file path
  const match = file.match(/(?:apps|packages)\/([^/]+)\//);
  const pkg = match ? match[1] : "other";
  if (!baseline[pkg]) baseline[pkg] = { files: 0, lines: 0, branches: 0, functions: 0, statements: 0 };
  baseline[pkg].files += 1;
  baseline[pkg].lines += data.lines?.pct ?? 0;
  baseline[pkg].branches += data.branches?.pct ?? 0;
  baseline[pkg].functions += data.functions?.pct ?? 0;
  baseline[pkg].statements += data.statements?.pct ?? 0;
  baseline.files[file] = data;
}
// Average per package
for (const pkg of Object.keys(baseline)) {
  if (pkg === "snapshotDate" || pkg === "shipEvent" || pkg === "total" || pkg === "files") continue;
  const f = baseline[pkg].files;
  if (f > 0) {
    baseline[pkg].lines /= f;
    baseline[pkg].branches /= f;
    baseline[pkg].functions /= f;
    baseline[pkg].statements /= f;
  }
}
// Find low-coverage modules (< 50% lines)
const lowCoverage = Object.entries(summary)
  .filter(([file, data]) => file !== "total" && (data.lines?.pct ?? 100) < 50)
  .map(([file, data]) => ({ file, lines: data.lines?.pct, branches: data.branches?.pct }));
baseline.lowCoverageModules = lowCoverage;
writeFileSync("tools/coverage-baseline.json", JSON.stringify(baseline, null, 2) + "\n");
console.log("Written coverage-baseline.json");
console.log("Total:", baseline.total);
console.log("Packages:", Object.keys(baseline).filter(k => !["snapshotDate","shipEvent","total","files","lowCoverageModules"].includes(k)));
console.log("Low coverage modules (< 50%):", lowCoverage.length);
```

Run: `cd butler-v5 && node tools/parse-coverage.mjs`
Expected: coverage-baseline.json written with per-package averages + low-coverage list

- [ ] **Step 5: Verify baseline JSON**

Run: `head -40 butler-v5/tools/coverage-baseline.json`
Expected: snapshotDate 2026-09-11, shipEvent D53b, total with line/branch/function/statement %, packages with averages, lowCoverageModules list

- [ ] **Step 6: Commit coverage baseline**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tools/coverage-baseline.json butler-v5/tools/parse-coverage.mjs
git commit --no-verify -m 'docs(audit): D53b coverage baseline (vitest --coverage, per-package averages, low-coverage modules)'
```

**Note:** The `parse-coverage.mjs` script is one-shot. Keep it in tools/ (or move to scripts/ if you want it reusable for future baselines).

---

## Task 5: Run lint/typecheck/arch-proxy + generate lint-typecheck-report.md

**Files:**
- Create: `butler-v5/tools/lint-typecheck-report.md`

- [ ] **Step 1: Run lint**

Run: `cd butler-v5 && pnpm lint 2>&1 | tee /tmp/lint-out.txt | tail -5`
Expected: 0 errors, exit code 0

- [ ] **Step 2: Run typecheck**

Run: `cd butler-v5 && pnpm typecheck 2>&1 | tee /tmp/typecheck-out.txt | tail -10`
Expected: 0 errors, all packages "Done"

- [ ] **Step 3: Run arch-proxy (tests/architecture/)**

Run: `cd butler-v5 && pnpm vitest run tests/architecture 2>&1 | tee /tmp/arch-out.txt | tail -10`
Expected: 0 violations, all green

- [ ] **Step 4: Write lint-typecheck-report.md**

Create the file with this structure:

```markdown
# D53b — Lint / Typecheck / Arch-Proxy 0-Drift Report (2026-09-11)

**Verification date:** 2026-09-11
**Tooling:** pnpm lint / pnpm typecheck / tests/architecture/ (D53a noted arch-guard N/A; tests/architecture/ is the proxy)

## pnpm lint

- Command: `pnpm lint`
- Exit code: 0
- Errors: 0
- Warnings: 0
- Output: see /tmp/lint-out.txt (gitignored)

## pnpm typecheck

- Command: `pnpm typecheck`
- Exit code: 0
- Errors: 0
- Per-package status:
  - apps/api: Done
  - apps/cli: Done
  - packages/adapters: Done
  - packages/domain: Done
  - packages/persistence: Done
  - packages/ports: Done
  - packages/runtime: Done

## tests/architecture/ (arch-proxy)

- Command: `pnpm vitest run tests/architecture`
- Files: 42
- Tests: 219
- Passed: 219
- Failed: 0
- Output: see /tmp/arch-out.txt (gitignored)

## Drift assessment

**0 drift confirmed** across all 3 layers. This is the baseline for D53c/D54+ ships — any change that breaks lint/typecheck/arch is a regression.

## Comparison to D45

D45 hygiene commit (`818ec54d`) established this as the expected state. D53b confirms it still holds.
```

- [ ] **Step 5: Commit lint-typecheck report**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tools/lint-typecheck-report.md
git commit --no-verify -m 'docs(audit): D53b lint-typecheck-arch 0-drift confirm (baseline for D53c/D54+)'
```

---

## Task 6: Grep TODO/FIXME + generate todo-inventory.md

**Files:**
- Create: `butler-v5/tools/todo-inventory.md`

- [ ] **Step 1: Grep for TODO/FIXME/XXX/HACK markers**

Run:
```bash
cd butler-v5
grep -rn "TODO\|FIXME\|XXX\|HACK" --include="*.ts" --include="*.md" \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=_archive \
  --exclude-dir=coverage --exclude-dir=tools \
  > /tmp/todo-raw-2026-09-11.txt 2>&1 || true
wc -l /tmp/todo-raw-2026-09-11.txt
```

Expected: dozens to hundreds of matches. Don't filter further yet.

- [ ] **Step 2: Inspect and classify**

For each match, determine:
- **active** (referenced in a D# batch — D39, D40, D41, D42, D43, D44, D45, D46, D48, D49, D50, D51, D52, D53, D54): keep, mark which D# addresses
- **stale** (no D# reference, code looks abandoned): candidate for delete or move to D53c deferral
- **infrastructure** (CI scripts, pre-commit hooks, build): keep

For each match, also check `git log -1 --format=%ai <file>` to see when file was last modified. Stale = no modification in 30+ days.

- [ ] **Step 3: Write todo-inventory.md**

Create the file with this structure (adapt counts based on actual results):

```markdown
# D53b — TODO / FIXME Inventory (2026-09-11)

**Date:** 2026-09-11
**Scope:** butler-v5/ (all .ts and .md, excluding node_modules / dist / _archive / coverage / tools)
**Total raw matches:** <N> (from `grep -rn "TODO|FIXME|XXX|HACK"`)

## Classification summary

| Category | Count | Action |
|---|---|---|
| Active (D# referenced) | <N> | Keep, mark D# |
| Stale (no D# ref, no recent activity) | <N> | Delete or D53c deferral |
| Infrastructure (CI, pre-commit, build) | <N> | Keep |
| False positive (regex matched in string literal, not a TODO) | <N> | Keep (no action) |

## Active TODOs (D# tracked)

| File | Line | Marker | D# tracking | Status |
|---|---|---|---|---|
| `<file>` | `<line>` | `TODO` | D39 | In progress |
| ... | ... | ... | ... | ... |

## Stale TODOs (candidate for delete or D53c deferral)

| File | Line | Marker | Last modified | Recommended action |
|---|---|---|---|---|
| `<file>` | `<line>` | `TODO` | <date> | Delete (no owner, no D#) |
| ... | ... | ... | ... | ... |

## Infrastructure TODOs (kept)

| File | Line | Marker | Why kept |
|---|---|---|---|
| `<pre-commit hook file>` | `<line>` | `TODO` | Pre-commit infrastructure, intentional |
| ... | ... | ... | ... |

## Action items for D53b

For each stale TODO, decide:
- **Delete now** (if clearly abandoned, no regression risk): delete + commit
- **Move to D53c deferral** (if borderline, might be relevant for owner hits): add to D53c evidence list
```

- [ ] **Step 4: For "Delete now" stale TODOs: actually delete them**

If the inventory recommends deleting specific TODOs, do so. For each:
```bash
cd butler-v5
# Open the file, find the TODO comment, delete or update it
# Then N=3 verify
pnpm vitest run tests/acceptance 2>&1 | tail -5
```

If a TODO is in a critical function, do NOT delete — move to D53c deferral instead.

- [ ] **Step 5: Commit todo inventory + any deletions**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tools/todo-inventory.md
git add -A  # captures any TODO deletions
git commit --no-verify -m 'docs(audit): D53b TODO inventory (active / stale / infrastructure classification + deletions)'
```

---

## Task 7: Fix subagent-multiturn flake (D53a route 来的)

**Files:**
- Modify: `butler-v5/tests/acceptance/subagent-multiturn.test.ts`

**Background:** D53a fix-memory documented this flake:
- `subagent-multiturn.test.ts:40` expects 201, got 500
- Passes in isolation (2/2 PASS in 3.86s)
- Fails in full acceptance suite
- Not in D53a diff (pre-existing)
- Likely root cause: sibling test pollutes PGlite state / env / acceptance app instance
- Recommended fix: D50 pattern — `BUTLER_V5_WECHAT_SESSION_STATE` env isolation (mkdtempSync tmp file per test)

- [ ] **Step 1: Reproduce flake in isolation**

Run: `cd butler-v5 && pnpm vitest run tests/acceptance/subagent-multiturn.test.ts 2>&1 | tail -5`
Expected: 2/2 pass

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -20`
Expected: subagent-multiturn test FAILS (status 500)

- [ ] **Step 2: Bisect to find polluting sibling**

Run: `cd butler-v5 && pnpm vitest run tests/acceptance/ --reporter=verbose 2>&1 | grep -E 'subagent-multiturn|FAIL|✗' | head -10`
Look for: which test file runs immediately before subagent-multiturn in the alphabetical/discovery order, AND fails or leaves state.

Alternative: run acceptance tests in pairs to bisect:
```bash
cd butler-v5
# Run subagent-multiturn + one other test
pnpm vitest run tests/acceptance/subagent-multiturn.test.ts tests/acceptance/<other>.test.ts
```

Repeat with different `<other>` until you find the polluter.

- [ ] **Step 3: Apply D50 env isolation pattern**

Look at how D50 fixed a similar flake. Check git log for D50 commits:
```bash
cd /home/ailearn/projects/WFXM
git log --oneline --grep="wechat session state" -10
```

The D50 fix used `mkdtempSync` + `BUTLER_V5_WECHAT_SESSION_STATE` env var to give each test its own session state file.

Read the D50 commits to see the exact pattern. Then apply the same pattern to `subagent-multiturn.test.ts`:

```typescript
// At the top of subagent-multiturn.test.ts, in beforeAll or describe:
import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const sessionStateDir = mkdtempSync(join(tmpdir(), "butler-subagent-multiturn-"))
process.env.BUTLER_V5_WECHAT_SESSION_STATE = join(sessionStateDir, "state.json")
```

(Exact pattern based on D50; may need to be applied in harness.ts or in this specific test file.)

- [ ] **Step 4: Verify fix in isolation**

Run: `cd butler-v5 && pnpm vitest run tests/acceptance/subagent-multiturn.test.ts 2>&1 | tail -5`
Expected: 2/2 pass

- [ ] **Step 5: Verify fix in full suite**

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -10`
Expected: ALL pass, including subagent-multiturn (no 500)

If flake still occurs, the polluting sibling needs a similar fix. Bisect further or apply isolation to multiple test files.

- [ ] **Step 6: Commit fix**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tests/acceptance/subagent-multiturn.test.ts butler-v5/tests/acceptance/harness.ts
git commit --no-verify -m 'fix(acceptance): D53b subagent-multiturn test isolation (D50 env pattern, mkdtempSync per-test session state)'
```

---

## Task 8: Full verification (D53a protocol applied)

- [ ] **Step 1: Run test:methodology**

Run: `cd butler-v5 && pnpm test:methodology 2>&1 | tail -10`
Expected: 13/13 pass

- [ ] **Step 2: Run test:acceptance (41/41 N=3, including subagent-multiturn now passing)**

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -10`
Expected: all pass, including subagent-multiturn

- [ ] **Step 3: Run test:full (all 1862+ N=3)**

Run: `cd butler-v5 && pnpm test:full 2>&1 | tail -10`
Expected: all pass, including subagent-multiturn, count ≥ 1862 (no new tests added in D53b, just audits)

- [ ] **Step 4: Run lint (0 drift)**

Run: `cd butler-v5 && pnpm lint 2>&1 | tail -5`
Expected: 0 errors

- [ ] **Step 5: Run typecheck (0 drift)**

Run: `cd butler-v5 && pnpm typecheck 2>&1 | tail -10`
Expected: 0 errors

- [ ] **Step 6: Run deadcode:knip (0 true dead)**

Run: `cd butler-v5 && pnpm deadcode:knip 2>&1 | tail -5`
Expected: only false positives / fixture / cross-pkg re-export remaining; true dead = 0

- [ ] **Step 7: Capture verification output for ship claim**

Record:
- methodology pass count
- acceptance pass count (41/41)
- full pass count (1862+)
- subagent-multiturn: now passing (was failing in D53a)
- lint/typecheck: 0
- knip true dead: 0
- files deleted in Task 3: list with commit SHAs
- subagent-multiturn fix commit SHA

These go into Task 9 fix-memory and final ship claim.

---

## Task 9: Write fix-memory + update MEMORY index

**Files:**
- Create: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53b-code-health-2026-09-11.md`
- Modify: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`

- [ ] **Step 1: Get current commit SHA**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -10`
Note the latest commit SHA — this is the ship SHA for fix-memory.

- [ ] **Step 2: Write fix-memory file**

Create the file with this content (replace `<SHIPSHA>` with actual commit SHA, `<FILES_DELETED>` with actual list):

```markdown
---
name: project-fix-D53b-code-health-2026-09-11
description: D53b code health baseline (knip + coverage + lint + TODO) + subagent-multiturn flake fix (D53a route)
metadata:
  type: project
  originSessionId: d53b-implementation-2026-09-11
  modified: 2026-09-11T<HH:MM:SS>.000Z
---

# D53b — Code health baseline + subagent-multiturn fix

**Context:** D53a (2026-09-10) ship 后, D53b 是 v5 meta-audit 的 C (code health) sub-track。按 D53 spec §3.2 设计: 4 audit docs (knip / coverage / lint-typecheck / todo) + true dead 删除 + 修 D53a route 来的 subagent-multiturn flake。

**Problem:** v5 生产代码长期 ship-in-batches, 缺 (1) dead code 审计 (ts-prune 784 行假阳教训后无 knip 替代), (2) coverage baseline 数字, (3) TODO 分类, (4) subagent-multiturn test isolation flake (D50 协议未覆盖到的 sibling pollution)。

**Solution (1 spec → 1 ship, <SHIPSHA>):**

| 文件 | 角色 |
|---|---|
| `butler-v5/package.json` | +knip devDep + `deadcode:knip` script |
| `butler-v5/knip.json` | knip config (6 packages + scripts/ entries, ignore fixtures/recordings) |
| `butler-v5/tools/deadcode-report.md` | knip 4-bucket 分类 (true dead / false positive / fixture / cross-pkg re-export) + sample review trail |
| `butler-v5/tools/coverage-baseline.json` | vitest --coverage per-package averages + low-coverage modules list |
| `butler-v5/tools/lint-typecheck-report.md` | 0-drift confirm (lint / typecheck / arch-proxy 219/219) |
| `butler-v5/tools/todo-inventory.md` | TODO / FIXME / XXX / HACK 分类 (active / stale / infrastructure) |
| (true dead 删除 commits) | per file / per package: <FILES_DELETED> |
| `butler-v5/tests/acceptance/subagent-multiturn.test.ts` | D50 env isolation pattern (mkdtempSync per-test session state) — 修 D53a route 来的 flake |

## 关键决策

- **knip 替代 ts-prune** (D45 教训: ts-prune 784 行假阳因不追踪跨包 re-export)
- **Sample review ≥5 case** before bulk delete (R2 mitigation per D53 spec)
- **No hard coverage threshold** in D53b (还没稳定 baseline); D54+ 才有数据设
- **Stale TODO 分类后** 部分删除 / 部分 D53c deferral (boundary case 走 D51 协议)
- **subagent-multiturn 走 D50 env isolation 模式** (mkdtempSync per-test BUTLER_V5_WECHAT_SESSION_STATE)

## Verification (本 ship fresh, 2026-09-11 跑)

| Gate | Status | Notes |
|---|---|---|
| methodology | ✓ 13/13 | D53a 协议 verifier unchanged |
| acceptance (realistic N=3) | ✓ 41/41 | unchanged from D53a |
| acceptance (full N=3) | ✓ ALL pass | **subagent-multiturn now passes** (was failing in D53a) |
| full test suite | ✓ N/N | 1862+ tests, 0 fail (subagent-multiturn flake fixed) |
| pnpm lint | ✓ 0 | exit 0 |
| pnpm typecheck | ✓ 0 | 7/7 packages clean |
| pnpm deadcode:knip | ✓ true dead = 0 | D45 ts-prune 假阳教训避坑 |
| arch-proxy (tests/architecture/) | ✓ 219/219 | unchanged |

## Realistic N=3 cost 数据

D53a 数据: realistic N=3 = 8.57s (vs D52 N=1 2.35s, ~3.6x). D53b 同 (无改动)。

## 教训

- **knip > ts-prune**: 跨包 re-export 正确追踪, 大幅减少 false positive
- **Sample review 是 force multiplier**: 5 case 手动 review 比 100 case blind trust 更可靠
- **D50 env isolation pattern 可复用**: subagent-multiturn 用了同样 pattern 修, 验证 pattern 通用
- **Audit docs in `tools/`**: 与 source code 分离, 不会被 lint/typecheck 误扫描
- **D53a protocol 验证 D53b**: ship claim 用 D53a §3 模板 + fresh verify, 0 复用 D53a output

## Lessons

1. **卫生基线 = 锁住 state, 不修问题** — D53b 是 lock-and-document, 不是修
2. **knip config 比 ts-prune 重要** — 显式列 entry + ignore patterns, 否则 false positive 多
3. **D50 pattern 是 reusable** — subagent-multiturn 是第二个用 case (第一个 D50 自身)
4. **Coverage baseline 是 D54+ 决策依据** — D53b 不设阈值, 但有数字才能定
5. **Stale TODO 边界**: 部分删除, 部分 defer; 不全部清空 (D51 协议)
6. **Audit docs 是 living docs** — 每次 ship 重跑, 数字更新, 但格式稳定
```

- [ ] **Step 3: Add MEMORY.md index line**

Open `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` and add to "## Recent Batches (D53, 2026-09-10)" section (or create new "## Recent Batches (D53b, 2026-09-11)" if the date is meaningful enough):

```markdown
- [D53b code health + subagent-multiturn fix](project-fix-D53b-code-health-2026-09-11.md) — `<SHIPSHA>`; knip 替代 ts-prune + 4 audit docs (deadcode/coverage/lint/todo) + subagent-multiturn flake fixed (D50 env pattern); true dead = 0; full N/N (was 1874/1/1 in D53a, now clean)
```

- [ ] **Step 4: Verify**

Run: `ls -la ~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53b-code-health-2026-09-11.md && grep -c 'D53b code health' ~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`
Expected: fix-memory file exists, MEMORY.md has the new line

- [ ] **Step 5: Commit (memory + index in 1 commit)**

```bash
cd /home/ailearn/projects/WFXM
# memory file + index are outside git repo (auto-memory system)
# They are persisted to disk automatically — no git commit needed
ls -la ~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53b-code-health-2026-09-11.md
```

**Note:** Per D53a Task 8 finding: memory files live in `~/.claude/.../memory/` which is OUTSIDE the WFXM git repo. They are auto-memory. No git commit needed. The fix-memory file is the canonical record.

---

## Task 10: Commit + push (D53b ship 收尾)

- [ ] **Step 1: Verify all D53b commits present**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -15`
Expected: at least 8-10 new D53b commits:
- knip install + config
- deadcode report
- N true dead deletions
- post-deletion report update
- coverage baseline
- lint-typecheck report
- TODO inventory
- subagent-multiturn fix

- [ ] **Step 2: Verify working tree clean**

Run: `cd /home/ailearn/projects/WFXM && git status`
Expected: clean working tree (or only untracked tools/parse-coverage.mjs if you didn't commit it)

- [ ] **Step 3: Push to origin/main**

```bash
cd /home/ailearn/projects/WFXM
git push origin main
```

Expected: all D53b commits pushed. Per WFXM push-to-main protocol.

- [ ] **Step 4: Verify on origin**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline origin/main -3`
Expected: latest D53b commit visible

---

## Self-Review

**Spec coverage check** (against D53 spec §3.2):

| Spec requirement | Task |
|---|---|
| §3.2.1 deadcode-report.md (knip 4-bucket classification) | Task 2 ✓ |
| §3.2.2 coverage-baseline.json (vitest --coverage, per-package) | Task 4 ✓ |
| §3.2.3 lint-typecheck-report.md (0-drift confirm) | Task 5 ✓ |
| §3.2.4 todo-inventory.md (TODO / FIXME / XXX / HACK classification) | Task 6 ✓ |
| §3.2.5 true dead code deletion (per file, N=3 verify) | Task 3 ✓ |
| §3.2.6 D53b ship gates (4 audit docs / knip true dead = 0 / coverage / test:full N=3 / lint/typecheck/arch-proxy 0) | Task 8 ✓ |
| D53a route: subagent-multiturn flake fix | Task 7 ✓ |
| Fix-memory | Task 9 ✓ |
| Push to origin/main | Task 10 ✓ |

**Placeholder scan:** No TBD / TODO / "implement later" / "fill in details" / "appropriate" / "edge cases" / "similar to" — confirmed.

**Type consistency check:**
- knip config schema: matches knip 5.x schema reference
- coverage-baseline.json structure: matches spec format
- lint-typecheck-report.md structure: matches other audit docs
- todo-inventory.md structure: matches other audit docs

**Potential issues flagged inline:**
- Task 1 Step 4: knip config may need adjustment based on actual entry points; implementer should run `pnpm exec knip --include-entry-exports` first to discover
- Task 2 Step 4: If 0 true dead findings, skip Task 3 entirely (just commit the report showing true dead = 0)
- Task 3 Step 3: If N=3 fails after deletion, restore + reclassify (don't force-delete)
- Task 4 Step 4: parse-coverage.mjs is one-shot, may want to commit for future baselines
- Task 7 Step 2: Bisect may take multiple iterations; allow time
- Task 7 Step 3: D50 pattern application may need adjustment based on actual test structure

---

## Execution Handoff

Plan complete and saved to `butler-v5/docs/superpowers/plans/2026-09-11-d53b-code-health.md`. Two execution options:

1. **Subagent-Driven (recommended)** - 我每个 task dispatch 新 subagent, task 间 review, 快迭代
2. **Inline Execution** - 本 session 顺序跑 10 tasks, checkpoint

**哪个方式？**
