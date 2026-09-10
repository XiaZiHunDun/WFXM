# D53 — v5 meta-audit (D + C + A 三 sub-track 设计文档)

> 来源：2026-09-10 owner 主动跳出 pause，问"服务还没到完美，怎么 check / evaluate / optimize"。Brainstorming 走 6 段 design 后确认 4 个盘点方向选 3 个 (D+C+A), B (drift 对账) 独立 D54。
>
> 范围：D53 = D (methodology) + C (code health) + A (deferral re-eval)。每 sub-track 1 spec / 1 plan / 1 ship (D53a / D53b / D53c)，顺序 D→C→A。
>
> 性质：混合型 (protocol + tool scan + doc-only)。B (drift) 显式不在 D53, 走 D54 独立 spec。

---

## 1. Context

### 1.1 起点

- 2026-09-08 D52 ship 后 v5 进入 pause (`94fd71df`)。D50 fresh verification 闭环 2 残留 latent bug 后 v5 production-ready。
- D48 owner 笔记抽 3 structural gaps (3.1 羊群 / 3.2 LLM 量化 / 3.3 chain 撤销)。D49 ship 关闭 3.3 (部分), D51 decline 3.1 + 3.2, D52 acceptance harness 扩 41 scenarios 闭环。
- v8 PRD candidate A/B/C 3/3 REVERT 实证 temperature model 单 round 不可靠 → D47 fixture-recording 同源风险未解除。
- 2026-09-10 owner 跳出 pause, 主动问 "服务还没到完美, 怎么 check / evaluate / optimize" → 4 方向 brainstorming 后选 D + C + A。

### 1.2 决策

- **D53 选 D + C + A 三 sub-track**。理由：D 是一切前提 (D47/D50 风险协议化); C 是最 cheap 卫生基线; A 是 doc-only 重新对齐 §18/§11.4/D48 触发状态。三 sub-track 独立 ship, 风险隔离。
- **D53 不含 B**。Drift 对账 (D49 5-type 缺口 / 6→5 phrases / memory invertible flag 等) 走 D54 独立 spec。B 必须等 D (D53a) 之后启, 否则 D47 REVERT 风险。
- **D53 不重启 §18 延后项 / D48 3 gaps / 新 feature / 架构变更 / 性能优化**。走 deferred-trigger-conditions 协议, 等 owner 撞点。

### 1.3 顺序 (依 D47/D50 风险)

```
D53a (0.5-0.7d, 协议基线)  →  D53b (0.4-0.5d, 工具扫描)  →  D53c (0.5-0.7d, doc 重评)
            ↓                            ↓                              ↓
     N=3 / prompt-freeze /           knip + coverage             §18 / §11.4 / D48
     fresh verification              + lint + todo                状态诚实记录
            ↓                            ↓                              ↓
        1 commit                     1+ commits                    1 commit (doc)
        ship D53a                    ship D53b                     ship D53c
```

D53a 是后续 D53b / D53c / D54 的协议基础, 必须在最前。

### 1.4 不在本批范围

- B track (drift 对账) → D54 spec
- §18 20 项延后建设 / D48 3 gaps 闭环 (3.1/3.2 已 decline, 3.3 D49 partial closure)
- 新 feature / 架构变更 / 性能优化
- §3/§20 架构不变量变更 (本批不动)

---

## 2. Architecture overview

D53 = 3 sub-track, 每个有独立 impl surface, 但共用 D53a 协议 (fresh verification + N=3 + prompt-freeze)。

```
D53a (methodology, 协议)
  ├─ docs/superpowers/notes/2026-09-10-d53a-methodology.md   (新, 7 段 protocol)
  ├─ tests/acceptance/recordings/.baseline-2026-09-10.json    (新, baseline snapshot)
  ├─ tests/acceptance/methodology.test.ts                    (新, verify 协议本身)
  └─ tests/acceptance/scenarios/realistic.test.ts            (retrofitted, 41 → N=3 wrap)

D53b (code health, 工具)
  ├─ tools/deadcode-report.md                                (新, knip 分类)
  ├─ tools/coverage-baseline.json                            (新, vitest coverage %)
  ├─ tools/lint-typecheck-report.md                          (新, 0-drift confirm)
  ├─ tools/todo-inventory.md                                 (新, TODO/FIXME 分类)
  └─ 删 true dead code (多 commit)

D53c (deferral re-eval, doc-only)
  ├─ docs/superpowers/notes/2026-09-10-d53c-deferral-reeval.md  (新, 7 段重评)
  ├─ DESIGN.md §18 / §11.4 status table 链接 refresh             (modify)
  ├─ D48 doc §3.1/§3.2/§3.3 evidence 补 D49/D52 SHA            (modify)
  └─ docs/superpowers/notes/2026-09-10-d54-drift-audit-entry.md (新, D54 handoff)
```

D53 整体无业务逻辑变更, 不动 packages/ 任何源码 (除 D53a realistic.test.ts retrofit 的 runner wrap + D53b true dead 删除)。

---

## 3. Components & Changes

### 3.1 D53a — Methodology

#### 3.1.1 `docs/superpowers/notes/2026-09-10-d53a-methodology.md` (新)

8 段 protocol doc (§0 Scope + §1-7 内容):

| § | 内容 |
|---|---|
| 0 | Scope — 适用 D# / P# / B# / C# / D5x 任何触 LLM code path 的 batch |
| 1 | **multi-round** — LLM test 跑 N≥3 round; 聚合规则 majority-or-all 可配 (默认 all = 3/3 pass 才算 pass; opt-in majority via env) |
| 2 | **prompt-freeze** — ship 期间 system prompt 在 ship 起点 snapshot 后冻结, 整 ship 不变; 中途要改 = 新 ship |
| 3 | **fresh verification** — ship claim 必须引用 "本 ship" 的 full verify 输出, 显式 pre-ship checklist 步骤 |
| 4 | baseline recording — 每个 protocol-compliant run 产 recordings/ baseline; 后续 run diff |
| 5 | retrofit checklist — 6-8 步把现有 test 升级为 protocol-compliant |
| 6 | anti-patterns — 禁单 round verdict / 禁 "信任 last batch green" / 禁 "prompt 中途改" |
| 7 | D47/D50 post-mortem — protocol 如何防这 2 个具体失败 (v8 PRD 3/3 REVERT 实证 + D50 ship-claim miss) |

#### 3.1.2 `tests/acceptance/recordings/.baseline-2026-09-10.json` (新)

D53a ship 时 recordings/ 状态 snapshot。结构:
```json
{
  "snapshotDate": "2026-09-10",
  "shipEvent": "D53a",
  "scenarios": {
    "A1": {...},
    "A2": {...},
    ...
  }
}
```

后续 ship 显式 diff 此 baseline; 偏差 ≥ 阈值 = fail。

#### 3.1.3 `tests/acceptance/methodology.test.ts` (新)

Verify 协议本身:
- N=3 round runner 存在 + wire
- baseline 对比函数能 work
- ship-claim 模板强引 "本 ship fresh verify output"
- 默认 all 聚合规则; majority opt-in via `BUTLER_V5_AGGREGATION=majority`
- fast iteration opt-out via `BUTLER_V5_MULTI_ROUND=0`

#### 3.1.4 `tests/acceptance/scenarios/realistic.test.ts` (retrofitted)

41 scenarios wrap 进 N=3 runner:
- 默认 N=3 (改 BUTLER_V5_MULTI_ROUND=0 fast iteration)
- 默认 all 聚合 (改 BUTLER_V5_AGGREGATION=majority)
- 渐进 retro: 1 demo scenario first (D2-chain-approval), 全量 41 在 ship 前

#### 3.1.5 D53a ship gates
- 4 files committed
- `pnpm test:methodology` passes (新增 ~10-20 case)
- `pnpm test:acceptance` 41/41 N=3 all pass
- `pnpm test:full` (1862 + ~20 new methodology) N=3 all pass
- `pnpm lint` / `pnpm typecheck` / `pnpm arch-guard` 0 drift
- baseline `.baseline-2026-09-10.json` committed
- 1 fix-memory: `project-fix-D53a-methodology-2026-09-10.md`

#### 3.1.6 D53a NOT in scope (留 D54+ 后续)
- Per-scenario cost 优化 (N=1 简单 / N=5 critical) — D54+ 评估
- Cross-ship baseline 多版本追踪 — D54+ 有 data 后
- Auto-revert on regression — D54+ ship 后

### 3.2 D53b — Code Health

#### 3.2.1 `tools/deadcode-report.md` (新)

knip 扫描结果分类:
- **true dead** (无 caller): 删
- **false positive** (knip 误报, 实际跨包 re-export): 标 archive, 不动
- **fixture** (test fixture, 看似 dead): 标 protected, 不动
- 至少 sample review 5 case 才动 true dead 类别 (D45 ts-prune 教训)

#### 3.2.2 `tools/coverage-baseline.json` (新)

vitest --coverage 全量结果:
```json
{
  "snapshotDate": "2026-09-10",
  "shipEvent": "D53b",
  "packages": {
    "api": { "lines": 87.3, "branches": 79.1, "functions": 91.2, "statements": 87.8 },
    "domain": {...},
    "ports": {...},
    "adapters": {...},
    "persistence": {...},
    "runtime": {...}
  },
  "lowCoverageModules": [...]  // < 50% critical
}
```

D53b 不设硬阈值 (还没稳定 baseline); D54+ 才有数据设。

#### 3.2.3 `tools/lint-typecheck-report.md` (新)

确认 0 drift (D45 后是 0, fresh verify):
- `pnpm lint` 输出 0
- `pnpm typecheck` 输出 0
- `pnpm arch-guard` 输出 0

如有 drift, fix 后重跑。

#### 3.2.4 `tools/todo-inventory.md` (新)

grep TODO / FIXME / XXX / HACK 全 repo, 分类:
- **active (有 D# 编号)**: 保留
- **stale (无关联, age > 30d)**: 删 或 移 D53c deferral
- **infrastructure (CI / pre-commit)**: 保留

#### 3.2.5 True dead code 删 (多 commit)

按 3.2.1 分类, true dead 删:
- 删前 grep 引用 + import
- 删后 N=3 跑 (catch flake from missing import)
- 按文件 1 commit / 文件, 或 batched per package

#### 3.2.6 D53b ship gates
- 4 audit docs committed
- `pnpm deadcode` (knip) true dead = 0 after fix
- `pnpm coverage` baseline `tools/coverage-baseline.json`
- `pnpm test:full` (1862 + 0 new) N=3 all pass
- `pnpm lint` / `pnpm typecheck` / `pnpm arch-guard` 0 drift
- 1 fix-memory: `project-fix-D53b-code-health-2026-09-10.md`

### 3.3 D53c — Deferral Re-eval

#### 3.3.1 `docs/superpowers/notes/2026-09-10-d53c-deferral-reeval.md` (新)

7-8 段重评 doc:

| § | 内容 | 来源 |
|---|---|---|
| 0 | Context + D38/D22/D48 起点 | D38 / D22 / D48 笔记 |
| 1 | §18 20 items D38→D53 重判 (逐项 evidence SHA) | D38 §18 表 + D39-D52 commits |
| 2 | §11.4 5 items 重判 (无新 trigger evidence) | D22 §11.4 表 |
| 3 | D48 3 gaps D53 重判 (3.1 / 3.2 / 3.3 evidence 补) | D48 §3 + D49 / D52 commits |
| 4 | D53a/b/c 自检 + D54 entry | 本 spec §1.3 / §4 |
| 5 | Verification gate (D53c 自身 + cross-link 一致) | — |
| 6 | Lessons (诚实 record 协议 / D48 3.1/3.2/3.3 状态如何) | D48 §7 + D51 协议 |
| 7 | D54 handoff 引用 | D54 entry doc |

#### 3.3.2 `DESIGN.md` §18 / §11.4 链接 refresh (modify)

- §18 line 815-816: 3 行 evidence 列加 D39-D52 SHA (D38 截止 → D53 截止)
- §11.4 line 565-573: 5 行 evidence 列加 D53c 重评日期
- D48 handoff 引用 1 处 link refresh

#### 3.3.3 D48 doc evidence 补 (modify)

修改 `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md`:
- §3.3 (line 95 段): "D49 partial closure (2 类 / 5 phrase)" evidence 加 D52 SHA + 计数细节
- §6 触发表 (line 167): D53c 重评日期标注 "2026-09-10 re-eval (D53c)"

不动 §3.1 / §3.2 (已 D51 decline)。

#### 3.3.4 `docs/superpowers/notes/2026-09-10-d54-drift-audit-entry.md` (新)

D54 handoff doc, 1-2 段:
- 引用 D52 acceptance harness (41 scenarios 含 5 D52 新 + D49 ship claim vs impl drift)
- 引用 D53c §18 / D48 重新评估 evidence
- D54 范围清晰: drift 闭环, doc review + impl fix (D49 5-type / 6→5 phrases / memory invertible flag / 新发现的)

#### 3.3.5 D53c ship gates
- 2 docs committed (reeval + D54 entry)
- `pnpm test:full` (1862 + 0 new) N=3 all pass (doc-only regression check)
- `pnpm lint` / `pnpm typecheck` / `pnpm arch-guard` 0 drift
- DESIGN.md / D48 doc 链接 cross-check 一致
- 1 fix-memory: `project-fix-D53c-deferral-reeval-2026-09-10.md`

---

## 4. Verification strategy

### 4.1 D53a protocol applied to D53 itself

每个 sub-track ship 走 D53a 确立的协议:
- **D53a ship**: protocol 是新的, verification = spec-defined ship gates (3.1.5)
- **D53b ship**: 用 D53a protocol — N=3 round on 41 scenarios (防删死代码时回归), fresh full verify
- **D53c ship**: 用 D53a protocol — N=3 round (doc-only 不应破但 verify), fresh full verify

### 4.2 Fresh verification (D53a §3) — 不可复用前 sub-track output

- D53a claim: 引用 D53a ship 自身 full verify (N=3 + lint + typecheck + arch-guard)
- D53b claim: 引用 D53b 自身 (含 N=3 + knip 0 true dead + coverage baseline)
- D53c claim: 引用 D53c 自身 (含 N=3 + design-vs-impl 0)

不可引用前 sub-track 的 output (D50 教训)。

### 4.3 Per-sub-track ship gates (汇总)

| Sub-track | test:methodology | test:acceptance N=3 | test:full N=3 | lint | typecheck | arch-guard | audit docs | fix-memory |
|---|---|---|---|---|---|---|---|---|
| D53a | ✓ (~20 new) | ✓ (41/41) | ✓ (1862+20 new) | 0 | 0 | 0 | methodology.md | D53a |
| D53b | ✓ (no new) | — | ✓ (1862) | 0 | 0 | 0 | 4 audit | D53b |
| D53c | ✓ (no new) | — | ✓ (1862) | 0 | 0 | 0 | 2 docs | D53c |

### 4.4 Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | D53a N=3 cost 涨 (41×3 vs 41) | High | Medium — CI +2x | 默认 N=3, fast iteration opt-out env; D54+ 评估 per-scenario N |
| R2 | D53b knip false positive (D45 ts-prune 教训 784 行假阳) | High | Medium — 修过头破架构 | sample review ≥ 5 case 才动; true dead 才删, false positive 标 archive |
| R3 | D53b 删 true dead 触发 latent import | Medium | High — test fail | 删前 grep 引用; 删后 N=3 跑 (catch flake) |
| R4 | D53c 评估主观 — "未撞" 边界 | Medium | Low — D51 协议不修 | 列 evidence SHA + counter; owner 可推翻 |
| R5 | D53a retrofit realistic 引入新 flake | Medium | Medium — protocol bug | 渐进 retro: 1 demo scenario first, 全量后置 |
| R6 | 跨 sub-track baseline 漂移 | Low | High — D53b 用错 baseline | D53a ship 立即 commit baseline; D53b 显式 verify 引用 |
| R7 | D47 REVERT 复发 (protocol 不彻底) | Low | High | D53a §7 显式列 v8 PRD REVERT 实证; methodology.test.ts 验 |
| R8 | D50 ship-claim miss 复发 | Low | High | pre-ship checklist 强引 "本 ship fresh verify"; methodology.test.ts 验 |

### 4.5 Anti-patterns (D53a §6) applied to D53

- ❌ D53b claim 引用 D53a green
- ❌ D53c ship 前不跑 full test ("doc-only 不必")
- ❌ D53a ship 前 single-round verdict
- ❌ D53 期间改 system prompt
- ❌ D53 ship 间不写 fix-memory

---

## 5. Files Changed (预估)

| 类型 | 路径 | 改动 | Sub-track |
|---|---|---|---|
| 新 | `butler-v5/docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` | 本 spec | (整体) |
| 新 | `butler-v5/docs/superpowers/notes/2026-09-10-d53a-methodology.md` | 7 段 protocol | D53a |
| 新 | `butler-v5/tests/acceptance/recordings/.baseline-2026-09-10.json` | baseline snapshot | D53a |
| 新 | `butler-v5/tests/acceptance/methodology.test.ts` | 协议 verify | D53a |
| 改 | `butler-v5/tests/acceptance/scenarios/realistic.test.ts` | N=3 wrap | D53a |
| 新 | `butler-v5/tools/deadcode-report.md` | knip 分类 | D53b |
| 新 | `butler-v5/tools/coverage-baseline.json` | vitest coverage | D53b |
| 新 | `butler-v5/tools/lint-typecheck-report.md` | 0-drift confirm | D53b |
| 新 | `butler-v5/tools/todo-inventory.md` | TODO 分类 | D53b |
| 改 | (true dead code 删除) | 多 commit | D53b |
| 新 | `butler-v5/docs/superpowers/notes/2026-09-10-d53c-deferral-reeval.md` | 7-8 段重评 | D53c |
| 改 | `butler-v5/DESIGN.md` | §18 / §11.4 链接 + evidence | D53c |
| 改 | `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` | §3.3 evidence 补 + §6 标 D53c | D53c |
| 新 | `butler-v5/docs/superpowers/notes/2026-09-10-d54-drift-audit-entry.md` | D54 handoff | D53c |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53a-methodology-2026-09-10.md` | memory | D53a |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53b-code-health-2026-09-10.md` | memory | D53b |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D53c-deferral-reeval-2026-09-10.md` | memory | D53c |
| 改 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` | +3 索引行 | 整体 |

预估:
- D53a: 4 文件 + memory + MEMORY 索引 = 5-7 commit (含 retrofit 渐进)
- D53b: 4 audit docs + true dead 删除多 commit + memory + 索引 = 5-15 commit (取决于 dead code 数量)
- D53c: 2 docs + DESIGN modify + D48 modify + memory + 索引 = 3-5 commit
- **D53 整体: 13-27 commit, 1.5-2 天 wall-clock**

---

## 6. v5 DESIGN alignment

- §3 / §20 架构不变量: D53a 协议 / D53b 工具扫描 / D53c doc 评审都不动 packages/ 业务源码 (除 D53a realistic.test.ts retrofit + D53b true dead 删除), 不触架构不变量
- §18 trigger guard: D53c 重新评估不删任何 arch guard, 仅补 evidence (D51 协议: owner 没撞 → 保留)
- §11.4 trigger guard: 同上, 不删
- §13 风险与自治: D53a protocol 显式承认 D47/D50 风险 → 防复发机制; D53c 诚实记录 D48 3 gaps 状态 → 符合 §20 #7 "明确不可撤销" 精神
- D48 doc SSOT: D53c 仅补 §3.3 evidence + §6 标 D53c 日期, 不动 §3.1/§3.2 (D51 已 decline) 和 §4/§5/§6/§7 观察内容

---

## 7. Commit 计划

按 WFXM doc-batch 模式 (D51 协议: doc batch + memory 分开 commit):

### D53a (1 ship)
1. commit 1 (code): realistic.test.ts retrofit + methodology.test.ts
2. commit 2 (data): baseline-2026-09-10.json
3. commit 3 (doc): d53a-methodology.md
4. commit 4 (memory): project-fix-D53a-methodology-2026-09-10.md + MEMORY.md 索引

### D53b (1 ship)
1. commit 1 (audit doc batch): 4 audit docs
2. commit 2...N (code): true dead 删除 per file / per package
3. commit N+1 (memory): project-fix-D53b-code-health-2026-09-10.md + MEMORY.md 索引

### D53c (1 ship)
1. commit 1 (doc batch): d53c-deferral-reeval.md + d54-drift-audit-entry.md + DESIGN.md + D48 doc
2. commit 2 (memory): project-fix-D53c-deferral-reeval-2026-09-10.md + MEMORY.md 索引

**Push 模式**: feature branch → main 直接 push (按 `feedback-wfxm-push-to-main` 协议)。

---

## 8. Lessons / 注意事项

- **D53 ≠ 新功能 = meta-audit**。D46/D44 是 feature ship, D48 是观察, D51 是 closure, D52 是 acceptance harness 扩, D53 是 meta-audit (协议 + 卫生 + 状态诚实)。每 batch 性质不同, 但都 ship-in-batches 模式一致。
- **D53a 协议必须 ship 在前**。B (drift) 必须等 D (D53a), 否则 D47 REVERT 风险 (v8 PRD 3/3 REVERT 实证)。
- **D53b sample review 至少 5 case**。D45 ts-prune 784 行假阳性教训; knip 替代但不保证 0 假阳。
- **D53c 不修不删**。仅 record evidence; 评估 subjective 但诚实 record 即可; owner 看到可推翻 (D51 协议)。
- **D53 ship 间不写合并 fix-memory**。D53a / D53b / D53c 各自独立 fix-memory + MEMORY 索引行, 便于 grep 反查 (D-batch 习惯)。
- **pre-commit hook 仍需 `--no-verify`**。D49 Task 6 fix 教训, 跨 sub-track 切换时尤其注意 (per `feedback-precommit-hook-flakiness`)。
- **D54 entry doc 必须在 D53c 内 ship**。否则 D54 brainstorming 缺 evidence 锚点, 走回头路。

---

**End D53 design doc.**
