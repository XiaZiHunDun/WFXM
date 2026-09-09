# D51 — 关闭 D48 §3.1/§3.2 两项结构 gap（设计文档）

> 来源：D48 owner 视角笔记 §3 "Owner 没识别但结构性问题 3 项"。D49 已 ship 关闭 §3.3（multi-tool chain 撤销）。
>
> 范围：D51 = §3.1 approval 羊群效应 + §3.2 LLM 质量量化不可达。两项**全部 decline（formalize + accepted gap）**，无新代码。
>
> 性质：纯 doc-only 闭环。DESIGN.md §18 + §11.4 加 decline row；D48 doc status 反转；新建 handoff note。

---

## 1. Context

### 1.1 D48 §3.1 / §3.2 自判

按 `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` §3：

| 项 | D48 自判 | 触发条件 |
|---|---|---|
| §3.1 approval 羊群效应 | "设计权衡，残余摩擦"。结构根因：policy-gate 无 trust 模式。 | owner 撞 1 次"误点 delete" |
| §3.2 LLM 质量量化不可达 | "方法论限制"。结构根因：temperature model + 单 round snapshot 不稳定；多 round + prompt freeze 4 min × N round 成本。 | owner 实测撞 "B 类某场景答错了" |
| §3.3 multi-tool chain 撤销 | D49 ship ✅ | — |

### 1.2 决策

**两项均 decline**：fixture harness 样本盲点 / 方法论限制；扩 fixture 成本高于潜在价值；等 owner 真撞 + multi-round methodology 固化后再评估。

**依据**：
- D48 笔记 §6 触发表 + §7 lessons 1-3
- v8 PRD candidate A/B/C 3/3 REVERT 实证（temperature model 单 round 不可靠）
- D-series owner-撞点触发协议（[`project-deferred-trigger-conditions-2026-09-01.md`](../../../../.claude/projects/-home-ailearn-projects-WFXM/memory/project-deferred-trigger-conditions-2026-09-01.md)）

### 1.3 不在本批范围

- §3.1 工程性 trust mode / approval grouping / summary — 无 owner 撞点数据
- §3.2 multi-round + prompt freeze methodology — D47 fixture-recording 同源风险未解除
- §18 其余 11 项延后 — 与 D51 独立（D51 后 §18 共 13 项）
- §11.4 其余 4 项基础设施 — 与 D51 独立（D51 后 §11.4 共 6 项）

---

## 2. Architecture overview

本批无新代码、无新机制、无新 wiring。**唯一改动**：4 处 doc 状态反转 + 1 处 handoff doc 新建。

```
DESIGN.md (架构 SSOT)
  ├─ §18 line 815-816     + 2 row (§3.1 + §3.2 declined)
  └─ §11.4 line 565-573   + 1 row (§3.2 methodology declined)

D48 doc (观察性笔记)
  ├─ §3.1/§3.2 段尾状态    "未识别" → "decline (2026-09-09 D51)"
  └─ §6 触发表 (line 173-177)  3 行 "⬜ 等触发" → "× declined (D51)"

D51 handoff doc (新增)
  └─ docs/superpowers/notes/2026-09-09-d51-decline-gaps.md  7 段结构

memory entry (新增)
  └─ project-fix-D51-decline-gaps-2026-09-09.md + MEMORY.md 索引
```

---

## 3. Components & Changes

### 3.1 DESIGN.md §18 新增 2 row

在 `butler-v5/DESIGN.md` line 813 后插入：

```markdown
- **信任模式 / Approval 羊群效应 (declined, 2026-09-09 D51)**：高频 Approval 触发会降低 owner 对真危险操作的警觉（肌肉记忆）。结构根因：policy-gate 无 trust 模式，仅 per-command 静态判定。触发条件：owner 撞 1 次"误点 delete"。**当前决定：decline** — fixture harness 样本盲点；35 场景剩 9 次非 read-only approval 已能表达摩擦；扩 fixture 成本高于潜在价值。详见 [`../docs/superpowers/notes/2026-09-09-d51-decline-gaps.md`](../docs/superpowers/notes/2026-09-09-d51-decline-gaps.md)。
- **LLM 输出质量量化 (declined, 2026-09-09 D51)**：结构根因：temperature model 单 round snapshot 不构成稳定 baseline；多 round + prompt freeze 才能稳定，但 4 min × N round 成本。**当前决定：decline** — 方法论限制 + v8 3/3 REVERT 同源风险；待 owner 实测撞"B 类某场景答错了"且能固化 multi-round methodology 才重新评估。
```

### 3.2 DESIGN.md §11.4 新增 1 row

在 `butler-v5/DESIGN.md` line 571 后插入：

```markdown
- LLM 质量量化方法论基础设施 (declined, 2026-09-09 D51)：multi-round + prompt freeze baseline 工具链。**当前决定：decline** — 见 §18 对应 row；D47 fixture-recording 同源风险未解除前不启。
```

### 3.3 D48 doc §3.1/§3.2 status 反转

修改 `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md`：

- §3.1 line 83: `**当前状态**：未识别。修选项 §18 没列入。` → `**当前状态**：decline (2026-09-09 D51，handoff doc `2026-09-09-d51-decline-gaps.md`)。修选项 §18 没列入且不再评估。`
- §3.2 line 92: `**当前状态**：未识别为"方法论限制"，列为"v8 candidate 待做"。D47 延续同源风险。` → `**当前状态**：decline (2026-09-09 D51，handoff doc)。方法论限制确认 + v8 3/3 REVERT 同源风险未解除前不启。`
- §6 触发表 line 176 (§3.1) + line 177 (§3.2): `⬜ 等触发` → `× declined (D51)`

### 3.4 D51 handoff doc (新建)

新建 `butler-v5/docs/superpowers/notes/2026-09-09-d51-decline-gaps.md`，7 段结构：

| § | 内容 | 来源 |
|---|---|---|
| 0 | Context + D48 自判 + D51 决策 | D48 §3.1/§3.2 + 本 spec §1 |
| 1 | §3.1 decline 理由（4 条：fixture harness 覆盖 / 9 次非 read-only approval 已实证 / 扩 fixture 成本 / trust mode 工程性假设无 owner 撞点验证） | D48 §3.1 + D44 P1-A 数据 |
| 2 | §3.2 decline 理由（4 条：temperature model 实证 / 4 min × N round 成本 / D47 fixture-recording 同源风险 / v8 3/3 REVERT） | D48 §3.2 + D47 + v8 PRD |
| 3 | DESIGN.md 集成位置 + 行号 | 本 spec §3.1 + §3.2 |
| 4 | D48 doc status flip + §6 触发表 row 状态 | 本 spec §3.3 |
| 5 | Verification gate（grep 行号 / D48 trigger 表完整性 / handoff doc 引用交叉对得上） | — |
| 6 | Lessons（fixture harness 样本盲点 ≠ 团队盲点 / 文档化 decline 是 closure 而非延后 / D-series owner-撞点协议再次验证） | D48 §7 |

### 3.5 memory entry

新建 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D51-decline-gaps-2026-09-09.md` + `MEMORY.md` 索引行（在"## Recent Batches (D50, 2026-09-09)" 段后加 "## Recent Batches (D51, 2026-09-09)" 小节）：

```
- [D51 §3.1/§3.2 decline](project-fix-D51-decline-gaps-2026-09-09.md) — 2 项 structural gap formalize + accepted gap; doc-only; 0 代码; DESIGN §18+§11.4 各加 row + D48 doc §3 status flip
```

---

## 4. Verification checklist

**doc-only 验证**（无 test/lint/typecheck）：

- [ ] DESIGN.md §18 line 813 后含 2 新 row，行号连续
- [ ] DESIGN.md §11.4 line 571 后含 1 新 row，行号连续
- [ ] D48 doc §3.1 line 83 状态含 "decline (2026-09-09 D51"
- [ ] D48 doc §3.2 line 92 状态含 "decline (2026-09-09 D51"
- [ ] D48 doc §6 触发表 2 行从 "⬜ 等触发" 改为 "× declined (D51)"
- [ ] D51 handoff doc 引用 DESIGN.md §18/§11.4 + D48 doc §3.1/§3.2/§6 行号对得上
- [ ] MEMORY.md 新增 1 行索引；新 memory file 内容与本 spec 一致
- [ ] git status 工作树只增不删（D48 doc 是 modify，DESIGN.md modify，handoff doc + memory file untracked）
- [ ] 0 业务代码改动

---

## 5. Files Changed (预估)

| 类型 | 路径 | 改动 |
|---|---|---|
| 改 | `butler-v5/DESIGN.md` | +3 row（§18 × 2 + §11.4 × 1） |
| 改 | `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` | §3.1/§3.2 status flip + §6 触发表 row 状态 |
| 新 | `butler-v5/docs/superpowers/notes/2026-09-09-d51-decline-gaps.md` | 7 段 handoff doc |
| 新 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D51-decline-gaps-2026-09-09.md` | memory entry |
| 改 | `~/.claude/projects/-home-ailearn-projects-WFXM/memory/MEMORY.md` | +1 索引行 |

预估 +60/-5 行（doc + memory），0 业务代码改动。

---

## 6. v5 DESIGN alignment

- §3 / §20 不变量：doc-only 改动不触架构不变量
- §18 trigger guard：本批**新增 2 row + 1 row + close status**，不撤销既有延后项
- §11.4 trigger guard：本批**新增 1 row + decline**
- §13 风险与自治：D51 = 把 §3.1/§3.2 从"未识别结构问题"显式转为"accepted gap"，符合 §20 #7 "明确不可撤销" 精神（scope 显式承认 = 不可逆决定的可审计声明）
- D48 doc SSOT：D51 仅 flip status + 引用，不改 D48 笔记本身观察内容

---

## 7. Commit 计划

按 WFXM doc-batch 模式 + D50 memory 分开 commit 模式：

1. **commit 1 (doc batch)**: DESIGN.md + D48 doc + D51 handoff doc — 1 commit
2. **commit 2 (memory)**: MEMORY.md 索引 + 新 memory file — 1 commit

**Push 模式**：feature → main 直接 push（按 `feedback-wfxm-push-to-main` 协议）。

---

## 8. Lessons / 注意事项

- **D51 ≠ 新功能 = 关闭/正式化**。doc-only closure 是 v5 production-ready 阶段的合法 batch（D46/D44 都是 feature ship；D48 是观察；D51 是 closure）。
- **不要 retry §3.1 trust mode** — D48 自判 fixture 样本盲点；扩 fixture 成本不划算；等 owner 真撞再启。
- **不要 retry §3.2 multi-round methodology** — D47 fixture-recording 同源风险未解除；D48 §7 lesson 1 明确"fixture harness 样本盲点"。
- **handoff doc 必须引用具体行号** — DESIGN.md line / D48 §X — 防止后续 drift。
- **MEMORY 索引行** — 按现有 D-series 索引格式（commit SHA 留空给 commit 后回填）。

---

**End D51 design doc.**