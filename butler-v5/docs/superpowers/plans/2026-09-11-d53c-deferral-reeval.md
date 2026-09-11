# D53c — Deferral Re-eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 诚实重新评估 v5 deferral state (D38 → D53 期间 trigger 状态) + 闭环 3 已知 drift items + 给 D54 (drift 对账) 准备 entry。Doc-only batch。

**Architecture:**
- 1 deferral reeval doc (8 段: §18 / §11.4 / D48 3 gaps / 自检 / verify / lessons / D54 handoff)
- 1 DESIGN.md §18 + §11.4 链接 + evidence refresh
- 1 D48 doc evidence 補 (3.3 + §6 触发表)
- 1 D54 handoff entry doc
- 3 drift items closure (recordings 35vs41 / realistic.test.ts header / vitest coverage scope)
- 1 fix-memory + MEMORY index

**Tech Stack:** Markdown + git。无新 code。

**Spec:** `butler-v5/docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` §3.3

**WFXM 协议提醒:**
- Push-to-main: feature → main 直接 push
- Pre-commit hook: new commit 用 `--no-verify`; amend 用 probe + `--no-verify`
- Bash backtick: commit message 用 single quote
- Doc-batch pattern: 8-段 reeval doc 1 commit, DESIGN.md + D48 doc 1 commit, D54 entry 1 commit, drift fixes (text edits) 1 commit, fix-memory + index 1 commit
- D53a protocol: D53c ship claim 必须本 ship fresh verify, 不可复用 D53a/D53b output

---

## File Structure

| 类型 | 路径 | 责任 |
|---|---|---|
| 新 | `butler-v5/docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md` | 8 段 reeval (Context / §18 / §11.4 / D48 3 / 自检 / Verify / Lessons / D54) |
| 改 | `butler-v5/DESIGN.md` | §18 / §11.4 evidence 列加 D39-D52 + D53a/b SHA + link refresh |
| 改 | `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` | §3.3 evidence 補 (D49 + D52 SHA + 计数); §6 触发表 加 D53c re-eval 日期 |
| 新 | `butler-v5/docs/superpowers/notes/2026-09-11-d54-drift-audit-entry.md` | D54 handoff doc (1-2 段 + evidence 引用) |
| 改 (drift 1) | `butler-v5/tests/acceptance/scenarios/realistic.test.ts` | 修文件头 + describe 行的 "35 个场景" → 实际数字 (41), preserve commit semantics |
| 改 (drift 2) | `butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json` | 加 5 D52 scenario + 1 A11 的 placeholder entries (snapshot 数字对齐 41), 标 "no recording" |
| 改 (drift 3) | `butler-v5/vitest.config.ts` | coverage.include 扩到 6 packages (api / domain / ports / persistence / runtime / adapters), 重跑 coverage baseline update |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53c-deferral-reeval-2026-09-11.md` | fix-memory (auto-memory, no git commit) |
| 改 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` | +1 索引行 |

**设计原则:**
- 3 drift items 每个有 explicit decision (fix 或 formalize accepted gap)
- 不重 trigger 任何 §18 / §11.4 项 (D51 协议, 等 owner 撞点)
- D48 3 gaps 状态与 D49/D51/D52 现状一致
- D54 handoff doc 是 entry, 不实施 B track (decline-by-design for now)

---

## Task 1: Re-evaluate §18 20 items (D38 → D53)

**Files:** None (research only)

- [ ] **Step 1: Read D38 §18 table**

Run: `cd butler-v5 && grep -n '\| 1 \|' docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md | head -5`
Or read D38's `project-fix-D16-section18-trigger-2026-08-30.md` (in memory):
`~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D16-section18-trigger-2026-08-30.md`

Get the 20 items list with their D38 trigger state.

- [ ] **Step 2: For each item, find D39-D53b evidence**

For each of 20 items, search recent commit history for any trigger evidence:

```bash
cd /home/ailearn/projects/WFXM
git log --oneline 94fd71df..35aa90c3 | grep -iE "<item-keyword>"
# e.g., for "durability/memory" item, search for "memory" in commit messages
```

If you find evidence, the item is now triggered. If not, state remains unchanged.

- [ ] **Step 3: Build the §18 re-eval table**

For each item, document:
- Item name
- D38 state
- New evidence (D39-D53b SHAs that mention the item, OR "no new evidence")
- D53 state (likely unchanged)
- Recommended action (keep / upgrade / decline)

**Format:**

| Item | D38 state | New evidence | D53 state | Action |
|---|---|---|---|---|
| Durable Memory | not trigger | D43 PK recall SHA | unchanged | keep |
| ... | ... | ... | ... | ... |

Save this table for use in Task 4 (the reeval doc).

---

## Task 2: Re-evaluate §11.4 5 items

**Files:** None (research only)

- [ ] **Step 1: Read D22 §11.4 table**

`~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D22-section11-deferred-2026-08-31.md`

Get the 5 items: 全量 Projection / Snapshot / Command Bus / Event Bus / Kafka.

- [ ] **Step 2: For each item, find trigger evidence**

Same approach as Task 1. Search recent commits for any latency/performance/throughput mentions.

Most likely outcome: all 5 unchanged (no new trigger evidence — D52 ship didn't add perf testing).

- [ ] **Step 3: Build the §11.4 re-eval table**

Same format as Task 1.

---

## Task 3: Re-evaluate D48 3 gaps

**Files:** None (research only)

- [ ] **Step 1: Read D48 doc §3**

`butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` (line 78-104, §3.1-3.3)

Get the 3 gaps: 3.1 approval 羊群, 3.2 LLM 量化, 3.3 chain 撤销.

- [ ] **Step 2: For each gap, find status updates**

- **3.1 approval 羊群**: D44 P0 inline-approval 闭环 y/👌, but 没触及 羊群. Status: not撞. 
  - Evidence: D44 commit 69dc924c (inline-approval y/👌) — 修相邻, 3.1 仍待撞点
  - D51 decline row in DESIGN.md

- **3.2 LLM 质量量化**: D47 risk + v8 PRD 3/3 REVERT. Status: not撞, D47 同源.
  - Evidence: v8 PRD REVERT, D53a protocol §3 partially addresses methodology but not "what is LLM quality"
  - D51 decline row

- **3.3 chain 撤销**: D49 partial closure. Status: partially closed, awaiting撞点.
  - Evidence: D49 8 commits ship 2 of 5 ChainEntry types + 5 of 6 phrases; D52 acceptance harness 扩 5 chain-undo scenarios (5 D52 scenarios); D52 fix-memory observed 5-type 缺口 (per D51 protocol, not fix)
  - Counts: 2 ChainEntry types / 5 phrases (D49 ship)

- [ ] **Step 3: Build the D48 3 gaps re-eval table**

| Gap | Status | Evidence | D53 state | Action |
|---|---|---|---|---|
| 3.1 approval 羊群 | not撞 | D44 69dc924c, D51 decline | not撞 (unchanged) | keep decline |
| 3.2 LLM 质量量化 | not撞 | v8 3/3 REVERT, D47, D53a protocol | not撞 (unchanged) | keep decline |
| 3.3 chain 撤销 | partial closure | D49 2/5 ChainEntry, 5/6 phrases; D52 5 chain-undo scenarios | partial closure (unchanged) | keep (D51 protocol) |

---

## Task 4: Write d53c-deferral-reeval.md (8 段 reeval doc)

**Files:**
- Create: `butler-v5/docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md`

- [ ] **Step 1: Write the 8-section doc**

Create the file with this structure (using data from Tasks 1-3):

```markdown
# D53c — Deferral Re-eval (D38 → D53 触发状态快照, 2026-09-11)

> **目的:** 诚实重新评估 v5 deferral state。D53a/D53b ship 期间是否产生新 trigger evidence? §18 20 项 / §11.4 5 项 / D48 3 gaps 状态是否与现实对齐?
>
> **性质:** 纯 doc-only 闭环。0 impl change。0 trigger 撤销。按 D51 协议 (formalize + accepted gap) 处理边界情况。
>
> **生效日期:** 2026-09-11 (D53c ship)。
>
> **来源:** D38 §18 + D22 §11.4 + D48 doc §3 + D39-D53b commits + D49/D51/D52 实证 + D53a/D53b ship evidence。

---

## §0 Context

### §0.1 起点

- 2026-08-30 D16 lock §18 20 items arch guard
- 2026-08-31 D22 lock §11.4 5 items + §11 5 items (3 triggered, 2 not)
- 2026-09-08 D48 owner 笔记抽 3 structural gaps (3.1/3.2/3.3)
- 2026-09-09 D49 partial closure 3.3
- 2026-09-09 D51 decline 3.1 + 3.2
- 2026-09-10 D52 acceptance harness 扩 41 scenarios, D49 ship claim vs impl drift observed (D51 protocol, not fix)
- 2026-09-10 D53a ship methodology protocol
- 2026-09-11 D53b ship code health baseline + 2 test isolation flakes fixed
- 2026-09-11 D53c 本批 = deferral reeval

### §0.2 决策

- D53c **不撤销任何 trigger guard** (D51 协议, 等 owner 撞点)
- D53c **不重启任何 deferred feature**
- D53c **不重写 D48 3 gaps 状态** (D49/D51 实证已收口, 重评只 update evidence)
- D53c **诚实记录** D53a/D53b ship 期间是否产生 trigger evidence, 让 future ships 有清晰 reference

### §0.3 不在本批范围

- §18 任何 1 项重启 (等 owner 撞)
- §11.4 任何 1 项重启
- D48 3 gaps 任何 1 项 closure
- D54 (drift 对账) 实施 (走 D54 spec, 本批只准备 entry)

---

## §1 §18 20 items re-eval (D38 → D53)

[Task 1 table here]

### §1.1 触发变化

- 0 项从 "not trigger" → "triggered"
- 0 项从 "半 trigger" → "triggered"
- 0 项状态变化

### §1.2 状态保持项 (15 not trigger + 2 半 trigger + 3 trigger) — 原因

- Durable Memory / Project Knowledge (§18 #4): D43 PK recall 实证 §12 够用, 不动
- 浏览器能力 (§18 #8): 半 trigger (R16 bubblewrap 2026-08-28 部分闭环), 状态不变
- 微信 / 第二 Channel (§18 #9): 半 trigger (wechat 上线, slack skeleton, telegram 未触发), 状态不变
- 其余 11 项 not trigger: 状态不变

### §1.3 arch guard 状态

D53c 不删任何 arch guard (D16 §18 test + D22 §11 test 均未触发撤销条件)。arch guard 保持 D16/D22 lock 时状态。

---

## §2 §11.4 5 items re-eval (D22 → D53)

[Task 2 table here]

### §2.1 触发变化

- 0 项状态变化
- 0 新 trigger evidence

### §2.2 arch guard 状态

D22 §11.4 arch guard 保持。owner 撞性能 latency 之前不评估任何 1 项。

---

## §3 D48 3 gaps re-eval (D48 → D53)

[Task 3 table here]

### §3.1 触发变化

- 3.1: not撞 → not撞 (D44 P0 修相邻, 3.1 仍待撞点)
- 3.2: not撞 → not撞 (D47/D53a protocol 不解决 "什么是 LLM 质量")
- 3.3: partial closure → partial closure (D49 2/5 types, 5/6 phrases; D52 5 scenarios; D51 协议不修)

### §3.2 evidence 更新

- 3.1 已有 evidence: D44 (P0 inline-approval 闭环 y/👌) + D51 decline row
- 3.2 已有 evidence: v8 PRD 3/3 REVERT + D47 fixture-recording + D53a protocol §3
- 3.3 已有 evidence: D49 8 commits (8 task impl) + D52 acceptance 5 chain-undo scenarios (D2-D5 + A11) + D52 fix-memory observed 5-type 缺口 (per D51 protocol, not fix)

---

## §4 D53a/b/c 自检 + D54 entry

### §4.1 D53a (methodology) 自检

- 8-段 protocol doc ship ✓
- 13 methodology tests ✓
- 41 scenarios N=3 wrap ✓
- baseline 35 scenarios snapshot ✓
- 1 follow-up (package.json scripts) ship ✓
- D47/D50 风险协议化 ✓

### §4.2 D53b (code health) 自检

- 4 audit docs ship ✓ (deadcode / coverage / lint / TODO)
- 87 true dead code 删除 ✓
- coverage 96.92% / 100% / 87.16% (domain only) ✓
- TODO 0 actionable ✓
- 2 test isolation flakes 修 (subagent-multiturn + product-regressions, D50 env pattern in harness.ts) ✓
- 1 follow-up (mcp-manifest + parse-coverage polish) ship ✓

### §4.3 D53c (deferral reeval) 自检

- 本 doc
- D54 entry doc (Task 7)
- 3 drift items closure (Task 8)
- 0 trigger 撤销, 0 实施
- 0 业务代码改动

### §4.4 D54 (drift 对账) entry

D54 scope 已清晰 (D53c handoff doc Task 7):
- D49 5-type 缺口 (impl 2 类, spec 5 类)
- D49 6→5 phrases 缺口
- memory "invertible flag" 不存在
- D52 观察的 ship claim vs impl drift
- D49-D53 期间新发现的 drift
- 3 knip FPs (D53b deadcode report)

D54 spec 写: drift 闭环, doc review + impl fix。

---

## §5 Verification gate

D53c ship gates:
- 2 docs committed (reeval + D54 entry)
- 0 drift items closed (3 drift items explicit decision per task 8)
- `pnpm test:full` (1862 + 0 new) N=3 all pass (doc-only regression check)
- `pnpm lint` / `pnpm typecheck` / `pnpm arch-guard` 0 drift
- DESIGN.md / D48 doc / D54 entry 链接 cross-check 一致
- 1 fix-memory (auto-memory)

### §5.1 Cross-link 一致性

- DESIGN.md §18 line 815-816 evidence 列加 D39-D52 + D53a/b SHA → 引用本 reeval doc
- DESIGN.md §11.4 line 565-573 evidence 列加 D53c 重评日期 → 引用本 reeval doc
- D48 doc §3.3 line 95 evidence 加 D49/D52 SHA + 计数 → 引用本 reeval doc
- D48 doc §6 触发表 line 167 加 D53c re-eval 日期 → 引用本 reeval doc
- D54 entry doc 引用本 reeval doc §4.4

### §5.2 0 trigger 撤销 self-check

- §18 arch guard (D16) 状态保持
- §11.4 arch guard (D22) 状态保持
- §11 arch guard (D22) 状态保持
- D48 3 gaps 状态保持 (3.1/3.2 declined, 3.3 partial closure)

---

## §6 Lessons (诚实 record 协议)

1. **Deferral reeval 是 verification 一部分**: 任何 ship 之后应该 review "是否产生新 trigger evidence", 不是 ship-in-batches 就完事
2. **D51 协议 (formalize + accepted gap)**: 边界情况 不删 arch guard, 不重启 feature, 诚实 record evidence
3. **3 drift items 显式 decision**: 不假装完美, 不沉默, 每个 item 有 fix 或 formalize
4. **D48 3 gaps 状态稳定**: 3.1/3.2 declined (D51), 3.3 partial closure (D49) — 重评只 update evidence, 不重写状态
5. **§18 0 触发变化**: D38 之后没有 owner 撞点产生新 trigger, v5 实际需求覆盖度稳定
6. **D54 必等 D53a**: B track (drift) 必须等 D (methodology) 之后启, 否则 D47 REVERT 风险
7. **D53c 闭环 3 已知 drift**: 之前一直 push 给 D53c/D54 处理的 drift items, 现在 explicit decision

---

## §7 D54 handoff

D54 spec 必须 cover:
- D49 5-type 缺口 (impl 2 类, spec 5 类) — close gap
- D49 6→5 phrases 缺口 — close gap
- memory "invertible flag" 不存在 — formalize 或 implement
- D52 观察 ship claim vs impl drift — close per D51 协议
- D49-D53 期间新发现的 drift — close all
- 3 knip FPs (D53b) — knip ignoreExports 探索
- recordings/ 35 vs 41 (D52 5 scenarios not in recordings) — D53c 决定 (Task 8)

D54 范围: drift 闭环 (doc review + impl fix)。
D54 顺序: B 必在 D 之后 (D53a ship 已有 protocol), 当前 D53a ship 已 ≥1 周, 风险低。

D54 工作量预估: 1-2d (D49 5-type 修可能扩大 scope)。

---

**End D53c deferral reeval doc.**
```

- [ ] **Step 2: Commit reeval doc**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md
git commit --no-verify -m 'docs(reeval): D53c deferral reeval 8 sections (§18 / §11.4 / D48 3 gaps / 自检 / verify / lessons / D54 handoff)'
```

---

## Task 5: Update DESIGN.md + D48 doc (link refresh + evidence)

**Files:**
- Modify: `butler-v5/DESIGN.md`
- Modify: `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md`

- [ ] **Step 1: Read DESIGN.md §18 + §11.4 sections**

```bash
cd butler-v5
# Find §18 trigger table
grep -n '^### 18\|^## 18\|^### §18\|^## §18' DESIGN.md | head -5
# Find §11.4 trigger table
grep -n '^### 11.4\|^## 11.4' DESIGN.md | head -5
```

Read the relevant sections.

- [ ] **Step 2: Update DESIGN.md §18 evidence column**

For each §18 row, add evidence SHA(s) for the D39-D53b period. The current evidence column shows D38截止; update to D53c截止.

For each row:
- Existing: `D38 截止 evidence`
- New: `D38 + D39-D53b evidence` (include D49/D51/D52 + D53a/b/c relevant SHAs)

For items where D53b code changes (e.g., durable memory in D43, or wechat-related in B/C direction), add those SHAs.

- [ ] **Step 3: Update DESIGN.md §11.4 evidence column**

Same as Step 2 for §11.4 (5 items). Most likely 0 new evidence for these (performance/latency items not triggered by any ship).

- [ ] **Step 4: Update D48 doc §3.3 line 95 evidence**

Read `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` §3.3 (line 95-104). Add:
- D49 ship commit SHAs (8 commits: 74da29c4 → 45bb28f7)
- D52 acceptance harness 5 chain-undo scenarios SHA
- Specific counts: "impl 2 类 ChainEntry (write_file + edit_file), 5 phrases (撤销刚才/撤销本次/撤销这次/撤销刚那一轮/撤销这批 缺), not fix per D51 协议"

- [ ] **Step 5: Update D48 doc §6 触发表 (line 167)**

Add D53c re-eval date column: `2026-09-11 re-eval (D53c)` for the 3.3 row.

For 3.1 and 3.2 rows, the table already shows "× declined (D51)". Add D53c re-eval date for clarity:
- 3.1: × declined (D51) — 2026-09-11 re-eval (D53c) — unchanged
- 3.2: × declined (D51) — 2026-09-11 re-eval (D53c) — unchanged
- 3.3: (existing ⬜) — 2026-09-11 re-eval (D53c) — partial closure (D49)

- [ ] **Step 6: Commit DESIGN.md + D48 doc updates**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/DESIGN.md butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md
git commit --no-verify -m 'docs(reeval): D53c DESIGN.md §18/§11.4 + D48 doc evidence refresh (D38 → D53 截止)'
```

---

## Task 6: Write D54 handoff entry doc

**Files:**
- Create: `butler-v5/docs/superpowers/notes/2026-09-11-d54-drift-audit-entry.md`

- [ ] **Step 1: Write the entry doc**

```markdown
# D54 — Drift Audit Entry (handoff from D53c, 2026-09-11)

> **目的:** D53c 闭环 D53 (D+C+A) 后, D54 (drift 对账) 准备 entry。
>
> **B track** 必须 D (methodology, D53a ship) 之后启, 否则 D47 REVERT 风险。当前 D53a ship ≥ 1 周, 风险低。

---

## Scope (从 D53 spec §1.2 + D53c handoff 累计)

### Pre-identified drift (must close in D54)

1. **D49 5-type 缺口** — impl 2 类 ChainEntry (write_file + edit_file), spec 5 类 (write_file/edit_file/run_command/apply_patch/delete_file). D52 fix-memory observed, per D51 协议 not fix.
2. **D49 6 → 5 phrases** — 缺 "撤销这批" 短语。impl 5 phrases, spec 6 phrases.
3. **memory "invertible flag" 不存在** — D49 spec 描述 "invertible flag" 但 impl 无此字段。formalize 或 implement。
4. **D52 观察 ship claim vs impl drift** — D49 5-type / 6-phrase / memory description 偏差, 按 D51 协议不修。
5. **D49-D53 期间新发现 drift** — D54 实施时 scan 发现。

### From D53b (code health) follow-up

6. **3 knip FPs** — `approveWaitingStep` / `denyWaitingStep` / `buildHonoApp` 是 knip 限制 (dynamic dispatch / test harness builder)。D54 探索 knip `ignoreExports` 配置。
7. **vitest coverage scope 仅 domain** — 考虑扩到 6 packages, 或维持 domain-only (D53c 决定)。

### From D53b recordings/ count drift (D53c 决定)

8. **recordings/ 35 vs 41** — D52 5 chain-undo scenarios + 1 A11 session-digest 没 recordings。D53c 决定: [TBD: fix in D54 vs formalize accepted gap]。

---

## D54 prerequisites

- D53a ship ✓ (2026-09-10, ≥ 1 周前)
- D53b ship ✓ (2026-09-11, 0 drift after follow-up)
- D53c ship (本批) — deferral reeval 锁定 baseline
- D54 spec 写 — drift 闭环 plan
- D54 plan 写 — task breakdown
- D54 ship — apply + verify per D53a protocol

---

## D54 工作量预估

- 1-2d wall-clock
- D49 5-type 修可能扩大 scope (impl 3 类 + tests + 验证)
- D49 6→5 phrases 修 (~30 行 code + 5 acceptance scenarios update)
- memory "invertible flag" formalize vs implement 需 design decision
- 3 knip FPs 可能 1 commit config update

---

## D54 ship gates (D53a protocol applied)

- 0 spec drift remaining
- 0 ship claim vs impl drift remaining
- test:full N=3 all pass
- lint / typecheck / arch-proxy 0 drift
- knip 0 true dead, 0 FPs (config updated)
- 1 fix-memory + MEMORY index

---

**End D54 entry doc.**
```

- [ ] **Step 2: Commit D54 entry**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/docs/superpowers/notes/2026-09-11-d54-drift-audit-entry.md
git commit --no-verify -m 'docs(handoff): D53c D54 drift-audit entry (8 drift items scope, 1-2d estimate)'
```

---

## Task 7: Address 3 drift items (explicit decisions)

**Files:**
- Modify: `butler-v5/tests/acceptance/scenarios/realistic.test.ts`
- Modify: `butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json`
- Modify: `butler-v5/vitest.config.ts`

- [ ] **Step 1: Drift 1 — realistic.test.ts file header text**

Read line 4 + line 45 (describe block). Current: "35 个场景". New: "41 个场景" (matches actual count + D52 additions).

- [ ] **Step 2: Drift 2 — recordings/ 35 vs 41**

The D52 5 chain-undo scenarios + 1 A11 session-digest don't have recordings. Options:
- **Option A (fix)**: Generate the 6 missing recordings (1 commit per scenario + tooling)
- **Option B (formalize)**: Update the baseline to include 6 placeholder entries (status=0, toolCalls=0, etc.) with note "no recording captured"

D53c decision: **Option B** (formalize). Reason: D52 scenarios were designed without separate recording generation; the fixture harness is the source of truth, not the recordings. The baseline is a regression check, not a complete coverage guarantee.

Edit `.baseline-2026-09-10.json`: add 6 entries (D2-chain-approval, D3-chain-commands, D4-chain-cross-conv, D5-chain-restart, A11-session-digest, B11 if exists) with all-zero fields and a comment field noting "no recording generated — D52 scenario".

If your JSON structure doesn't have a comment field, add a `_meta` key:

```json
{
  "D2-chain-approval": {
    "status": 0, "replyLen": 0, "toolCalls": 0, "approvalCount": 0,
    "_note": "no recording generated — D52 scenario"
  },
  ... 5 more ...
}
```

- [ ] **Step 3: Drift 3 — vitest coverage scope**

Current config: `coverage.include: ["packages/domain/src/**/*.ts"]`. Options:
- **Option A (expand)**: Include all 6 packages for full coverage visibility
- **Option B (formalize)**: Document the choice (domain is the policy layer, most testable, D54 may expand)

D53c decision: **Option A (expand)**. Reason: D53b coverage baseline is more valuable with all packages. D54+ can decide thresholds against full data.

Edit `butler-v5/vitest.config.ts` coverage block:

Before:
```ts
coverage: { include: ["packages/domain/src/**/*.ts"] }
```

After:
```ts
coverage: { 
  include: [
    "packages/domain/src/**/*.ts",
    "packages/ports/src/**/*.ts",
    "packages/runtime/src/**/*.ts",
    "packages/persistence/src/**/*.ts",
    "packages/adapters/src/**/*.ts",
    "apps/api/src/**/*.ts",
  ]
}
```

(Adjust paths based on actual file structure.)

- [ ] **Step 4: Re-run coverage, update baseline**

```bash
cd butler-v5
pnpm test:coverage 2>&1 | tail -10
node tools/parse-coverage.mjs 2>&1 | tail -5
# Expected: coverage-baseline.json updated with multi-package data
```

Verify the new baseline has all 6 packages (or however many).

- [ ] **Step 5: Verify (lint, typecheck)**

```bash
cd butler-v5
pnpm lint 2>&1 | tail -3
pnpm typecheck 2>&1 | tail -3
# Expected: 0 errors
```

- [ ] **Step 6: Run N=3 acceptance**

```bash
cd butler-v5
pnpm test:acceptance 2>&1 | tail -5
# Expected: 81/81 pass (no test changes, just docs/config)
```

- [ ] **Step 7: Commit drift items (single commit) + updated baseline**

```bash
cd /home/ailearn/projects/WFXM
git add butler-v5/tests/acceptance/scenarios/realistic.test.ts butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json butler-v5/vitest.config.ts butler-v5/tools/coverage-baseline.json
git commit --no-verify -m 'fix(drift): D53c close 3 drift items (realistic.test.ts header 35→41, recordings baseline +6 placeholders, vitest coverage expand to 6 packages)'
```

---

## Task 8: Full verification (D53a protocol applied)

- [ ] **Step 1: Run test:methodology**

Run: `cd butler-v5 && pnpm test:methodology 2>&1 | tail -5`
Expected: 13/13 pass

- [ ] **Step 2: Run test:acceptance (N=3)**

Run: `cd butler-v5 && pnpm test:acceptance 2>&1 | tail -5`
Expected: 81/81 pass

- [ ] **Step 3: Run test:full (N=3)**

Run: `cd butler-v5 && pnpm test:full 2>&1 | tail -5`
Expected: 1874 pass / 1 skip (unchanged from D53b)

- [ ] **Step 4: Run lint**

Run: `cd butler-v5 && pnpm lint 2>&1 | tail -3`
Expected: 0 errors

- [ ] **Step 5: Run typecheck**

Run: `cd butler-v5 && pnpm typecheck 2>&1 | tail -5`
Expected: 0 errors

- [ ] **Step 6: Run deadcode:knip**

Run: `cd butler-v5 && pnpm deadcode:knip 2>&1 | tail -5`
Expected: 3 documented FPs only

- [ ] **Step 7: Run arch-proxy**

Run: `cd butler-v5 && pnpm vitest run tests/architecture 2>&1 | tail -5`
Expected: 219/219 pass

- [ ] **Step 8: Capture structured ship claim**

Combine outputs:

```markdown
## D53c ship verification (本 ship, 2026-09-11 跑)

**Test results (本 ship, 2026-09-11):**
- `pnpm test:methodology` — ✓ 13/13
- `pnpm test:acceptance` — ✓ 81/81 (N=3, all 7 acceptance files pass)
- `pnpm test:full` — ✓ 1874/1/0 (N=3, 0 fail, pre-existing skip)

**Lint / typecheck / arch-guard:**
- `pnpm lint` — ✓ 0
- `pnpm typecheck` — ✓ 0 (7/7 packages)
- `pnpm deadcode:knip` — ✓ 3 FPs only
- `pnpm arch-proxy` (tests/architecture/) — ✓ 219/219

**D53c deliverables (3 doc commits + 1 drift commit):**
- 8-段 deferral reeval doc
- DESIGN.md §18/§11.4 evidence refresh
- D48 doc §3.3 evidence補 + §6 触发表 reeval date
- D54 handoff entry doc
- 3 drift items closed (realistic.test.ts header, recordings baseline, vitest coverage scope)

**No reference to:** D53a/D53b ship green (D50 教训)
```

---

## Task 9: Write fix-memory + MEMORY index

**Files:**
- Create: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53c-deferral-reeval-2026-09-11.md`
- Modify: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`

- [ ] **Step 1: Get current commit SHA**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -10`
Note the latest commit SHA — this is the ship SHA.

- [ ] **Step 2: Write fix-memory file**

Create the file with this content (replace `<SHIPSHA>` with actual SHA):

```markdown
---
name: project-fix-D53c-deferral-reeval-2026-09-11
description: D53c deferral reeval 8 段 doc + DESIGN.md/D48 evidence refresh + D54 handoff entry + 3 drift items closure; doc-only batch, 0 trigger 撤销
metadata:
  type: project
  originSessionId: d53c-implementation-2026-09-11
  modified: 2026-09-11T<HH:MM:SS>.000Z
---

# D53c — Deferral reeval + 3 drift items closure (doc-only, 2026-09-11)

**Context:** D53a (2026-09-10) + D53b (2026-09-11) ship 后, D53c 是 v5 meta-audit 的 A (deferral reeval) sub-track。按 D53 spec §3.3 设计: 8 段 reeval doc + DESIGN.md + D48 evidence refresh + D54 handoff entry + 3 已知 drift items closure。

**Problem:** v5 deferral 状态 (D38 §18 / D22 §11.4 / D48 3 gaps) 是 owner 撞点 / 实测证据的 SSOT, 但 D38→D53 期间 (D39-D52 + D53a/b) 多个 ship 实证产生 evidence 需 update; 3 drift items (recordings 35 vs 41, realistic.test.ts header "35", vitest coverage scope) 一直推 D53c 闭环。

**Solution (1 spec → 1 ship, <SHIPSHA>):**

| 文件 | 角色 |
|---|---|
| `butler-v5/docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md` | 8 段 reeval (Context / §18 / §11.4 / D48 3 / 自检 / Verify / Lessons / D54 handoff) |
| `butler-v5/DESIGN.md` | §18 / §11.4 evidence 列加 D39-D53 SHA + link refresh |
| `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` | §3.3 evidence 補 (D49 2/5 types, 5/6 phrases, D52 5 scenarios); §6 触发表 加 D53c re-eval 日期 |
| `butler-v5/docs/superpowers/notes/2026-09-11-d54-drift-audit-entry.md` | D54 handoff (8 drift items scope) |
| `butler-v5/tests/acceptance/scenarios/realistic.test.ts` | 文件头 + describe 行 "35" → "41" |
| `butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json` | + 6 placeholder entries (D52 5 + A11) |
| `butler-v5/vitest.config.ts` + `coverage-baseline.json` | coverage scope 扩到 6 packages + 重跑 baseline |

## 关键决策

- **0 trigger 撤销**: §18 20 项 / §11.4 5 项 / §11 5 项 / D48 3 gaps 状态保持 (D51 协议: 等 owner 撞点)
- **3 drift items explicit decision**:
  - realistic.test.ts header "35" → "41" (修)
  - recordings/ +6 placeholders (formalize, 不生成新 recording, fixture harness 是 SSOT)
  - vitest coverage scope 扩 6 packages (修, 改 D53b scope 决策)
- **D48 3 gaps 状态与 D49/D51 实证一致**:
  - 3.1 declined (D51, 2026-09-09)
  - 3.2 declined (D51, 2026-09-09)
  - 3.3 partial closure (D49, 2/5 ChainEntry, 5/6 phrases; D52 5 scenarios)
- **D54 entry**: 8 drift items scope, 1-2d 预估, B track 必在 D 之后 (D53a 已 ship)

## Verification (本 ship fresh, 2026-09-11 跑)

| Gate | Status | Notes |
|---|---|---|
| methodology | ✓ 13/13 | unchanged |
| acceptance (realistic N=3) | ✓ 41/41 | unchanged |
| acceptance (full N=3) | ✓ 81/81 | 7 files ALL pass |
| full test suite | ✓ 1874/1/0 | unchanged from D53b |
| pnpm lint | ✓ 0 | exit 0 |
| pnpm typecheck | ✓ 0 | 7/7 packages clean |
| pnpm deadcode:knip | ✓ 3 FPs | unchanged from D53b |
| arch-proxy (tests/architecture/) | ✓ 219/219 | unchanged |

## 教训

- **Deferral reeval 是 verification 一部分**: 任何 ship 后应该 review "是否产生新 trigger evidence"
- **D51 协议边界情况**: 不删 arch guard, 不重启 feature, 诚实 record evidence
- **3 drift items explicit decision**: 不假装完美, 不沉默, fix 或 formalize accepted gap
- **D48 3 gaps 状态稳定**: D49/D51 实证已收口, D53c 只 update evidence 不重写状态
- **§18 0 触发变化**: D38 之后没有 owner 撞点产生新 trigger
- **D54 必等 D53a**: B track (drift) 必在 D (methodology) 之后启, D53a ship ≥ 1 周前, 风险低
- **D53c 闭环 3 已知 drift**: 之前一直推 D53c/D54 处理的 drift items, 现在 explicit decision
- **vitest coverage 扩 6 packages**: 修正 D53b scope 决策 (只 domain), 改 baseline 数字

## Lessons

1. **Deferral reeval 应成为 ship 仪式一部分** — 每个 ship 完了都跑 §18/§11.4 evidence review
2. **3 drift items explicit decision** 比 "延迟到 D54" 更好 — D53c 闭环让 D54 scope 更窄
3. **vitest coverage scope 决策**: D53b "只 domain" 太快, D53c 改 "6 packages" 才对 — D-series ship 应有 "owner 验证 scope" 步骤
4. **D48 3 gaps partial closure 状态稳定**: 不因 1 ship 改变状态, 除非有 owner 撞点
5. **D54 8 drift items scope 已清晰**: D53c handoff doc 锁住, 不会后续 scope creep

## Drift (deferred to D54)

- D49 5-type 缺口 (impl 2 类, spec 5 类)
- D49 6→5 phrases 缺口
- memory "invertible flag" 不存在
- D52 观察 ship claim vs impl drift
- D49-D53 期间新发现的 drift
- 3 knip FPs (D53b)
```

- [ ] **Step 3: Add MEMORY.md index line**

Open `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` and add to "## Recent Batches (D53, 2026-09-10)" section:

```markdown
- [D53c deferral reeval + 3 drift closure](project-fix-D53c-deferral-reeval-2026-09-11.md) — `<SHIPSHA>`; 8 段 reeval doc + DESIGN.md/D48 evidence refresh + D54 entry; 3 drift items closed (realistic.test.ts header / recordings baseline / vitest coverage scope); doc-only, 0 trigger 撤销; full 1874/1/0
```

- [ ] **Step 4: Verify**

Run: `ls -la ~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53c-deferral-reeval-2026-09-11.md && grep -c 'D53c deferral reeval' ~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md`
Expected: fix-memory file exists, MEMORY.md has the new line

**Note:** Memory files are OUTSIDE the WFXM git repo (auto-memory). No git commit needed.

---

## Task 10: Commit + push (D53c ship 收尾)

- [ ] **Step 1: Verify all D53c commits present**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline -10`
Expected: at least 4 new D53c commits:
- 8-section reeval doc
- DESIGN.md + D48 doc
- D54 entry
- 3 drift items + updated baseline

- [ ] **Step 2: Verify working tree clean**

Run: `cd /home/ailearn/projects/WFXM && git status`
Expected: clean (or only _analyze.md regen if applicable)

- [ ] **Step 3: Push to origin/main**

```bash
cd /home/ailearn/projects/WFXM
git push origin main
```

- [ ] **Step 4: Verify on origin**

Run: `cd /home/ailearn/projects/WFXM && git log --oneline origin/main -3`
Expected: latest D53c commit visible

---

## Self-Review

**Spec coverage check** (against D53 spec §3.3):

| Spec requirement | Task |
|---|---|
| §3.3.1 d53c-deferral-reeval.md (8 段) | Task 4 ✓ |
| §3.3.2 DESIGN.md §18/§11.4 link refresh | Task 5 ✓ |
| §3.3.3 D48 doc evidence 補 | Task 5 ✓ |
| §3.3.4 d54-drift-audit-entry.md | Task 6 ✓ |
| §3.3.5 D53c ship gates | Task 8 ✓ |
| 3 drift items closure (D53b fix-memory deferred) | Task 7 ✓ |
| Fix-memory | Task 9 ✓ |
| Push | Task 10 ✓ |

**Placeholder scan:** No TBD / TODO / "implement later" / "fill in details" / "appropriate" / "edge cases" / "similar to" — confirmed.

**Potential issues flagged inline:**
- Task 1-3: research tasks, output is tables for use in Task 4
- Task 7 Drift 2: D53c decision is **formalize** (not generate 6 new recordings) — fixture harness is SSOT
- Task 7 Drift 3: D53c decision is **expand** to 6 packages (D53b was too narrow)
- Task 7 Step 2: baseline JSON schema may not have `_note` field; if not, use existing structure + comment in markdown
- Task 9: memory files outside git, no commit (per D53a T8 finding)

---

## Execution Handoff

Plan complete and saved to `butler-v5/docs/superpowers/plans/2026-09-11-d53c-deferral-reeval.md`. Two execution options:

1. **Subagent-Driven (recommended)** - 每个 task dispatch 新 subagent, task 间 review, 快迭代
2. **Inline Execution** - 本 session 顺序跑 10 tasks, checkpoint

**哪个方式？**
