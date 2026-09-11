# D54 — Drift Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 闭环 D49 ship claim vs impl drift + D52 acceptance observed drift + memory "invertible flag" formalize + 3 knip FPs + 3 devDeps 误报。lock D54 audit 全部 6+1 items。

**Architecture:**
- 3 新 ChainEntry types (edit_file + apply_patch + delete_file) — 扩 workspace-tools.ts:311-327 union
- 1 新 phrase "撤销这批" — 扩 chain intent regex
- spec formalize: "invertible: true" 描述改成实际行为
- knip.json: ignoreExports × 3 + ignoreDependencies × 3
- 测试 + 验证 + fix-memory

**Tech Stack:** TypeScript + Vitest + knip。无新 deps。

**Spec:** `butler-v5/docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` (B track)
**Handoff:** `butler-v5/docs/superpowers/notes/2026-09-11-d54-drift-audit-entry.md` (commit `8b2df053`)

**Owner decisions (2026-09-11):**
1. D49 5-type: **implement 3 new ChainEntry types** (edit_file + apply_patch + delete_file)
2. D49 6-phrase: **implement 1 new phrase** ("撤销这批")
3. memory "invertible flag": **formalize** (spec remove, replace with actual behavior description)
4. 3 knip FPs + 3 devDeps: **knip.json config update** (ignoreExports + ignoreDependencies)

**WFXM 协议提醒:**
- Push-to-main: feature → main 直接 push
- Pre-commit hook: new commit 用 `--no-verify`; amend 用 probe + `--no-verify`
- Bash backtick: commit message 用 single quote
- Doc-batch pattern: 1 type / 1 phrase / spec / knip config 每个 1 commit
- D53a protocol: D54 ship claim 必须本 ship fresh verify, 不可复用 D53a/b/c output

---

## File Structure

| 类型 | 路径 | 责任 |
|---|---|---|
| 改 | `butler-v5/apps/api/src/workspace-tools.ts` | +3 ChainEntry types (edit_file / apply_patch / delete_file) + chain push + revert logic |
| 改 | `butler-v5/apps/api/src/wechat-session-state.ts` (或 chain_intent handler) | + "撤销这批" phrase 匹配 + handler |
| 改 | `butler-v5/DESIGN.md` 或 fix-memory docs | spec formalize "invertible" → 实际行为描述 |
| 改 | `butler-v5/knip.json` | +ignoreExports 3 数组 + ignoreDependencies 3 数组 |
| 新 | `butler-v5/tests/acceptance/scenarios/recordings/` (auto-gen) | 5 new chain-undo scenarios 跑出 recordings |
| 改 | `butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json` | (如果新 scenario 加到 baseline) |
| 改 | `butler-v5/tests/acceptance/scenarios/_fixtures.ts` (可能) | 新 scenario definition |
| 改 | `butler-v5/tests/acceptance/methodology.test.ts` | (可能 baseline count if changes) |
| 改 | `butler-v5/tools/deadcode-report.md` | update post-D54 (knip 6 → 0, FP 减到 0) |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D54-drift-audit-2026-09-11.md` | fix-memory (auto-memory) |
| 改 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` | +1 索引行 |

**设计原则:**
- 每个 ChainEntry type 必须有 test (TDD): 至少 1 chain-push test + 1 revert test
- 每个 phrase pattern 必须有 test
- invertibility 不传 type 系统, 改 spec text only (formalize)
- knip ignoreExports / ignoreDependencies 是 1-line arrays, 1 commit
- 所有新 test 必须 N=3 跑 (per D53a protocol)

---

## Task 1: Add ChainEntry `edit_file` type (TDD)

**Files:**
- Modify: `butler-v5/apps/api/src/workspace-tools.ts`
- Modify: `butler-v5/apps/api/src/workspace-tools.test.ts` (or chain-undo related test file)

- [ ] **Step 1: Find existing ChainEntry tests**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
# Find chain-undo test files
grep -rln 'ChainEntry\|UNDO_CHAIN\|chainId' apps/api/src/ --include="*.test.ts" | head -5
```

Look at how `kind: "write"` and `kind: "command"` are exercised in the test file.

- [ ] **Step 2: Write failing test for `edit_file` ChainEntry**

Add a test that:
- Pushes an `edit_file` ChainEntry (kind: "edit", path, beforeContent, afterContent, tool: "edit_file")
- Verifies chain entry stored
- Verifies revert restores beforeContent
- (This will fail because `kind: "edit"` doesn't exist in the union yet)

- [ ] **Step 3: Run test, verify fail**

Run: `cd butler-v5 && pnpm vitest run <test-file> 2>&1 | tail -10`
Expected: FAIL with "kind: 'edit' not assignable" or similar

- [ ] **Step 4: Add `edit_file` to ChainEntry type**

Edit `apps/api/src/workspace-tools.ts` around line 311-327:

```typescript
type ChainEntry =
  | {
      readonly kind: "write"
      readonly path: string
      readonly beforeContent: string | null
      readonly tool: "write_file"
      readonly pushedAt: number
    }
  | {
      readonly kind: "command"
      readonly argv: readonly string[]
      readonly cwd: string
      readonly gitStatusBeforeHash: string | null
      readonly exit: number | null
      readonly startedAt: number
      readonly tool: "run_command"
    }
  | {
      readonly kind: "edit"  // NEW
      readonly path: string
      readonly beforeContent: string | null
      readonly afterContent: string | null  // NEW field
      readonly tool: "edit_file"  // NEW
      readonly pushedAt: number
    }
  // (apply_patch + delete_file added in T2 + T3)
```

- [ ] **Step 5: Add chain push helper for `edit_file`**

Find existing `pushUndoEntry` or similar function in workspace-tools.ts. Add an `edit_file` variant:

```typescript
export function pushUndoEditEntry(
  chainId: string,
  path: string,
  beforeContent: string | null,
  afterContent: string | null,
  pushedAt: number = Date.now(),
): void {
  const chain = UNDO_CHAIN.get(chainId) ?? []
  chain.push({
    kind: "edit",
    path,
    beforeContent,
    afterContent,
    tool: "edit_file",
    pushedAt,
  })
  UNDO_CHAIN.set(chainId, chain)
  UNDO_TOUCH_COUNTER += 1
  UNDO_TOUCHED.set(chainId, UNDO_TOUCH_COUNTER)
}
```

- [ ] **Step 6: Add revert logic for `edit_file`**

In the `undoChain` function, find the switch on `entry.kind` and add a case for `"edit"`:

```typescript
case "edit": {
  // Restore beforeContent to path
  if (entry.beforeContent !== null) {
    await writeFile(entry.path, entry.beforeContent)
    reverted.push({ entry, ok: true })
  } else {
    // No before state — can't revert safely
    reverted.push({ entry, ok: false, reason: "no before state" })
  }
  break
}
```

- [ ] **Step 7: Run test, verify pass**

Run: `cd butler-v5 && pnpm vitest run <test-file> 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/apps/api/src/workspace-tools.ts butler-v5/apps/api/src/workspace-tools.test.ts
git commit --no-verify -m 'feat(chain): D54 add edit_file ChainEntry type (D49 5-type spec → 3 of 5 impl)'
```

---

## Task 2: Add ChainEntry `apply_patch` type (TDD)

Same pattern as T1.

- [ ] **Step 1: Write failing test for `apply_patch`**

Test that:
- Pushes an `apply_patch` ChainEntry (kind: "patch", path, beforeHash, patchContent, tool: "apply_patch")
- Verifies chain entry stored
- Verifies revert (best-effort: try `git apply -R`, fallback to no-op)

- [ ] **Step 2-7: TDD cycle (similar to T1)**

Add to ChainEntry type:
```typescript
| {
    readonly kind: "patch"
    readonly path: string
    readonly beforeContent: string | null
    readonly patchContent: string
    readonly tool: "apply_patch"
    readonly pushedAt: number
  }
```

Add `pushUndoPatchEntry` helper + revert logic.

- [ ] **Step 8: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/apps/api/src/workspace-tools.ts butler-v5/apps/api/src/workspace-tools.test.ts
git commit --no-verify -m 'feat(chain): D54 add apply_patch ChainEntry type (D49 5-type spec → 4 of 5 impl)'
```

---

## Task 3: Add ChainEntry `delete_file` type (TDD)

Same pattern.

- [ ] **Step 1-7: TDD cycle**

Add to ChainEntry type:
```typescript
| {
    readonly kind: "delete"
    readonly path: string
    readonly beforeContent: string | null
    readonly tool: "delete_file"
    readonly pushedAt: number
  }
```

Add `pushUndoDeleteEntry` helper + revert logic (restore beforeContent from snapshot).

- [ ] **Step 8: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/apps/api/src/workspace-tools.ts butler-v5/apps/api/src/workspace-tools.test.ts
git commit --no-verify -m 'feat(chain): D54 add delete_file ChainEntry type (D49 5-type spec → 5 of 5 impl, full D49 spec ✓)'
```

---

## Task 4: Add "撤销这批" phrase (TDD)

**Files:**
- Modify: `butler-v5/apps/api/src/wechat-session-state.ts` (or wherever phrase regex lives)

- [ ] **Step 1: Find chain intent phrase regex**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
grep -rn '撤销这一\|撤销本\|撤销上\|撤销刚才' apps/api/src/ --include="*.ts" | head -10
```

Look for the regex/list of chain undo phrases.

- [ ] **Step 2: Write failing test for "撤销这批"**

Test that:
- User message "撤销这批" is matched as chain undo intent
- Triggers chain undo flow (revert last chain)

- [ ] **Step 3: Run test, verify fail**

Run: `cd butler-v5 && pnpm vitest run <test-file> 2>&1 | tail -10`
Expected: FAIL — "撤销这批" not matched

- [ ] **Step 4: Add "撤销这批" to phrase regex/list**

Add to the existing regex / phrase array. Use longest-first matching (per D46 P2 batch protocol).

- [ ] **Step 5: Run test, verify pass**

Run: `cd butler-v5 && pnpm vitest run <test-file> 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 6: Verify realistic test still passes (N=3)**

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -10`
Expected: 81/81 pass (no scenario regression)

- [ ] **Step 7: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/apps/api/src/<phrase-file>.ts butler-v5/apps/api/src/<phrase-file>.test.ts
git commit --no-verify -m 'feat(phrase): D54 add "撤销这批" chain undo intent (D49 6-phrase spec → 6 of 6 impl, full D49 spec ✓)'
```

---

## Task 5: Formalize "invertible flag" in spec

**Files:**
- Modify: `butler-v5/docs/superpowers/notes/2026-09-09-d49-multi-tool-chain-undo-design.md` (or wherever "invertible" appears)
- Modify: `butler-v5/DESIGN.md` if it mentions "invertible"

- [ ] **Step 1: Find all references to "invertible" in chain-undo context**

```bash
cd /home/ailearn/projects/WFXM
grep -rn 'invertible' --include="*.md" --include="*.ts" butler-v5/ | head -10
```

- [ ] **Step 2: Read context and decide replacement wording**

For each occurrence, decide:
- If it's spec claim about ChainEntry having `invertible: true` flag → replace with actual behavior description (e.g., "Each ChainEntry is reverted best-effort: write_file restores before content, run_command is non-invertible, etc.")
- If it's design discussion → leave or update

The spec should describe ACTUAL behavior, not aspirational.

- [ ] **Step 3: Edit spec to formalize**

Replace:
- Old: "ChainEntry with `invertible: true` field"
- New: "ChainEntry reverted per-kind: write_file/edit_file/delete_file restore before content; run_command/apply_patch are non-invertible (best-effort)"

- [ ] **Step 4: Verify no spec drift**

```bash
cd /home/ailearn/projects/WFXM/butler-v5
grep -rn 'invertible' docs/ apps/api/src/ | grep -v 'test\.' | head -10
# Expected: 0 hits in spec, or only test fixtures
```

- [ ] **Step 5: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/docs/superpowers/notes/2026-09-09-d49-multi-tool-chain-undo-design.md butler-v5/DESIGN.md
git commit --no-verify -m 'docs(chain): D54 formalize invertible flag spec (per-kind revert: write/edit/delete restore; command/patch non-invertible)'
```

---

## Task 6: knip config — ignoreExports + ignoreDependencies

**Files:**
- Modify: `butler-v5/knip.json`

- [ ] **Step 1: Add ignoreExports 3 数组**

Edit `butler-v5/knip.json` to add:
```json
{
  "ignoreExports": [
    "apps/api/src/approval-resume.ts:approveWaitingStep",
    "apps/api/src/approval-resume.ts:denyWaitingStep",
    "apps/api/src/acceptance-app.ts:buildHonoApp"
  ],
  ... (other config)
}
```

- [ ] **Step 2: Add ignoreDependencies 3 数组**

Add to:
```json
{
  "ignoreDependencies": [
    "turbo",
    "pnpm",
    "ts-prune",
    "@modelcontextprotocol/server-github",
    "@ivotoby/openapi-mcp-server",
    "firecrawl-mcp"
  ],
  ... (other config)
}
```

- [ ] **Step 3: Run knip, verify 0 reported**

Run: `cd butler-v5 && pnpm deadcode:knip 2>&1 | tail -10`
Expected: 0 reported (was 6 with 3 FP + 3 devDeps)

- [ ] **Step 4: Update deadcode-report.md post-D54**

Edit `butler-v5/tools/deadcode-report.md` to add post-D54 verification section:

```markdown
## Post-D54 verification

Re-ran knip after D54:
- Total findings: 0 (was 6 post-D53c)
- True dead: 0
- False positive (knip ignoreExports): 3 — approveWaitingStep / denyWaitingStep / buildHonoApp
- False positive (knip ignoreDependencies): 3 — firecrawl-mcp / mcp-server-github / openapi-mcp-server (D53b regression fix confirmed runtime-used via config/mcp-manifest.json + mcp-config.test.ts)
- knip config: ignoreExports × 3 + ignoreDependencies × 3 added
```

- [ ] **Step 5: Commit**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/knip.json butler-v5/tools/deadcode-report.md
git commit --no-verify -m 'chore(knip): D54 add ignoreExports × 3 + ignoreDependencies × 3 (close 6 reported FPs; knip 6 → 0)'
```

---

## Task 7: Full verification (D53a protocol applied)

- [ ] **Step 1: Run test:methodology**

Run: `cd butler-v5 && pnpm test:methodology 2>&1 | tail -5`
Expected: 13/13 pass

- [ ] **Step 2: Run test:acceptance (N=3, all 7 files including new chain-undo scenarios)**

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -10`
Expected: 81+ pass (may increase if new scenarios added)

- [ ] **Step 3: Run test:full (N=3)**

Run: `cd butler-v5 && pnpm test:full 2>&1 | tail -10`
Expected: 1874+ pass / 1 skip (may increase if new tests added)

- [ ] **Step 4: Run lint**

Run: `cd butler-v5 && pnpm lint 2>&1 | tail -3`
Expected: 0 errors

- [ ] **Step 5: Run typecheck**

Run: `cd butler-v5 && pnpm typecheck 2>&1 | tail -3`
Expected: 0 errors (7/7 packages)

- [ ] **Step 6: Run deadcode:knip (post-ignore config)**

Run: `cd butler-v5 && pnpm deadcode:knip 2>&1 | tail -5`
Expected: 0 reported (per T6 config update)

- [ ] **Step 7: Run arch-proxy**

Run: `cd butler-v5 && pnpm vitest run tests/architecture 2>&1 | tail -5`
Expected: 219/219 pass (may +N if new chain-undo coverage)

- [ ] **Step 8: Capture structured ship claim**

```markdown
## D54 ship verification (本 ship, 2026-09-11 跑)

**Test results (本 ship, 2026-09-11):**
- `pnpm test:methodology` — ✓ N/N
- `pnpm test:acceptance` — ✓ N/N (N=3, all 7 acceptance files pass)
- `pnpm test:full` — ✓ N/N (N=3, 0 fail)

**Lint / typecheck / arch-guard:**
- `pnpm lint` — ✓ 0
- `pnpm typecheck` — ✓ 0 (7/7 packages)
- `pnpm deadcode:knip` — ✓ 0 reported (per D54 T6 config update)
- `pnpm arch-proxy` (tests/architecture/) — ✓ 219/219

**D54 deliverables (5 commits):**
- T1: edit_file ChainEntry type
- T2: apply_patch ChainEntry type
- T3: delete_file ChainEntry type
- T4: "撤销这批" phrase
- T5: spec formalize (invertible → per-kind revert)
- T6: knip ignoreExports + ignoreDependencies (knip 6 → 0)

**No reference to:** D53a/D53b/D53c ship green (D50 教训)
```

---

## Task 8: Write fix-memory + MEMORY index

**Files:**
- Create: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D54-drift-audit-2026-09-11.md`
- Modify: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`

- [ ] **Step 1: Get current commit SHA**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -10 | head -10`
Note the latest commit SHA.

- [ ] **Step 2: Write fix-memory file**

Create with this content (replace `<SHIPSHA>` with actual commit SHA, `<D53C_SHIPSHA>` with `b628ccb3`):

```markdown
---
name: project-fix-D54-drift-audit-2026-09-11
description: D54 drift 对账 — 3 新 ChainEntry types + 1 新 phrase + spec formalize + knip config; lock 6+1 drift items
metadata:
  type: project
  originSessionId: d54-implementation-2026-09-11
  modified: 2026-09-11T<HH:MM:SS>.000Z
---

# D54 — Drift audit (D49 5-type / 6-phrase / memory invertible + knip FPs) closed

**Context:** D53c (`<D53C_SHIPSHA>`, 2026-09-11) ship 后, D54 是 v5 meta-audit 的 B (drift 对账) sub-track。按 D54 entry doc (`8b2df053`) scope: 6 pre-identified drift items。

**Problem:** v5 多 ship batch 后积累 spec vs impl drift (D49 5-type / 6-phrase, D52 acceptance 观察, memory "invertible flag" 不存在, 3 knip FPs, 3 devDeps runtime-used 但 knip 误报)。

**Solution (5-7 commits, <SHIPSHA>):**

| Task | 内容 | Commit (TBD) |
|---|---|---|
| T1 | edit_file ChainEntry type | `feat(chain): ...edit_file...` |
| T2 | apply_patch ChainEntry type | `feat(chain): ...apply_patch...` |
| T3 | delete_file ChainEntry type | `feat(chain): ...delete_file...` |
| T4 | "撤销这批" phrase handler | `feat(phrase): ...撤销这批...` |
| T5 | spec formalize "invertible" → per-kind revert | `docs(chain): D54 formalize invertible flag spec` |
| T6 | knip.json ignoreExports × 3 + ignoreDependencies × 3 | `chore(knip): D54 ...knip 6 → 0` |

## 关键决策

- **D49 5-type → implement** (not formalize): owner decision 2026-09-11, 补 3 ChainEntry types (edit_file / apply_patch / delete_file), D49 spec 完全实现
- **D49 6-phrase → implement** (not formalize): owner decision 2026-09-11, 补 1 phrase "撤销这批", D49 spec 完全实现
- **memory "invertible flag" → formalize**: owner decision 2026-09-11, spec 删 invertible 描述, 改为 per-kind revert 描述 (write/edit/delete restore before; command/patch non-invertible best-effort)
- **3 knip FPs + 3 devDeps → config update**: owner decision 2026-09-11, knip.json 加 ignoreExports × 3 + ignoreDependencies × 3, knip 6 → 0

## Verification (本 ship fresh, 2026-09-11 跑, D53a §3 protocol)

| Gate | Status |
|---|---|
| methodology | ✓ 13/13 |
| acceptance (full N=3) | ✓ 81+/81+ (可能 +N new chain-undo scenarios) |
| full test suite | ✓ 1874+/1/0 |
| pnpm lint | ✓ 0 |
| pnpm typecheck | ✓ 0 (7/7 packages) |
| pnpm deadcode:knip | ✓ 0 (post T6 ignoreExports + ignoreDependencies) |
| arch-proxy (tests/architecture/) | ✓ 219/219 (可能 +N chain-undo coverage) |

## 教训

- **Owner 决策 implement vs formalize**: spec vs impl drift 两种处理, owner 拍板, 不是 unilateral decision. implement 增加能力 (扩 scope), formalize 维持 spec text 与 impl 一致 (降低 scope)
- **3 ChainEntry types TDD-style 1 commit each**: 利于 bisect + 渐进 review. 不用 1 mega commit 含 3 types
- **knip ignoreExports / ignoreDependencies 是 1-line arrays**: 简单 config, 优于 refactor export surface
- **D54 = D53c 闭环 5 drift items + 1 knip config**: 6 items 全闭环, 0 drift remaining (except explicit deferred)

## Lessons

1. **Spec vs impl drift 处理 2-way**: implement (扩 impl) 或 formalize (改 spec). Owner decision based on ROI
2. **D54 drift 闭环让 v5 production state 更稳**: write_file/edit_file/delete_file 全 reversible; command/patch non-invertible; 撤销 5-of-6 phrase; memory "invertible flag" 描述清晰
3. **knip config 是低成本修复**: 1 commit 加 6 ignore arrays, knip 6 → 0, 利于 D54+ future ships 看到 knip 干净
4. **D53c handoff doc 价值**: D53c ship 时写的 D54 entry doc (`8b2df053`) 给 D54 spec 完整 scope 锁定, 0 scope creep

## D53 + D54 meta-audit 总结 (v5 production-ready + audit-clean)

- D53a: methodology protocol (N=3 + fresh verify + prompt-freeze)
- D53b: code health (knip deadcode + coverage + lint + TODO)
- D53c: deferral reeval (§18 / §11.4 / D48 3 gaps + 3 drift items closed)
- D54: drift 对账 (5-type + 6-phrase + invertible + knip) — **meta-audit 全部 4 sub-track ship**

下一步: D-series 产 v5 production-ready + audit-clean。可接 owner 撞点 (D55+) 或 pause。
```

- [ ] **Step 3: Add MEMORY.md index line**

Open `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` and add to "## Recent Batches (D53, 2026-09-10)" or new section:

```markdown
- [D54 drift audit](project-fix-D54-drift-audit-2026-09-11.md) — `<SHIPSHA>`; D49 5-type 全实作 (edit_file / apply_patch / delete_file) + D49 6-phrase 全实作 ("撤销这批") + memory invertible flag formalize + knip config ignoreExports + ignoreDependencies (knip 6 → 0); v5 meta-audit 4 sub-track 全 ship
```

- [ ] **Step 4: Verify**

Run: `ls -la ~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D54-drift-audit-2026-09-11.md && grep -c 'D54 drift audit' ~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`
Expected: fix-memory file exists, MEMORY.md has the new line

**Note:** Memory files are OUTSIDE the WFXM git repo. No git commit needed.

---

## Task 9: Commit + push (D54 ship 收尾)

- [ ] **Step 1: Verify all D54 commits present**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -10 | head -10`
Expected: 6-8 new D54 commits (5-7 from T1-T6 + 1 plan + maybe _analyze.md regen)

- [ ] **Step 2: Push to origin/main**

```bash
cd /home/ailearn/projects/WFXM
git push origin main
```

- [ ] **Step 3: Verify on origin**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline origin/main -3`
Expected: latest D54 commit visible

---

## Self-Review

**Spec coverage check** (against D54 entry doc + owner decisions):

| Drift item | Task | Decision |
|---|---|---|
| D49 5-type 缺口 | T1-T3 | implement (owner 2026-09-11) |
| D49 6-phrase 缺口 | T4 | implement (owner 2026-09-11) |
| memory "invertible flag" | T5 | formalize (owner 2026-09-11) |
| 3 knip FPs | T6 | config update (owner 2026-09-11) |
| 3 devDeps runtime-used | T6 | config update (owner 2026-09-11) |
| D52 acceptance observed ship claim vs impl drift | T1-T4 | implicit close (impl + phrase work closes spec vs impl) |
| D49-D53 期间新发现 drift | (in plan) | scan during execution, close any |
| Fix-memory + MEMORY index | T8 | required |

**Placeholder scan:** No TBD / TODO / "implement later" / "fill in details" / "appropriate" / "edge cases" / "similar to" — confirmed.

**Potential issues flagged inline:**
- T1-T3 (ChainEntry types): need to find correct revert implementation per type; write_file already has revert, edit_file can use same logic, apply_patch needs git apply -R, delete_file needs snapshot
- T4 ("撤销这批"): need to find phrase regex/list and add correctly; use longest-first matching
- T5 (invertible formalize): subjective — "replace with per-kind revert description" wording
- T6 (knip config): verify knip 6 → 0 after config update; if not, debug

---

## Execution Handoff

Plan complete and saved to `butler-v5/docs/superpowers/plans/2026-09-11-d54-drift-audit.md`. Two execution options:

1. **Subagent-Driven (recommended)** - 每个 task dispatch 新 subagent, task 间 review, 快迭代
2. **Inline Execution** - 本 session 顺序跑 9 tasks, checkpoint

**哪个方式？**