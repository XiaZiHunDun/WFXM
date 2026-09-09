# D51 — 关闭 D48 §3.1 / §3.2 两项结构 gap（handoff）

> 来源：D48 owner 视角笔记 §3 "Owner 没识别但结构性问题 3 项"。
>
> 范围：D51 = §3.1 approval 羊群效应 + §3.2 LLM 质量量化不可达。两项**全部 decline（formalize + accepted gap）**，无新代码。
>
> spec：[`../specs/2026-09-09-d51-decline-gaps-design.md`](../specs/2026-09-09-d51-decline-gaps-design.md)

---

## 0. Context + 决策

D48 §3 列出 3 项 owner 视角下结构性 gap：

| 项 | 状态 |
|---|---|
| §3.1 approval 羊群效应 | ✅ declined (D51, 2026-09-09) |
| §3.2 LLM 质量量化不可达 | ✅ declined (D51, 2026-09-09) |
| §3.3 multi-tool chain 撤销 | ✅ shipped (D49, 2026-09-09) |

D51 = 把 §3.1/§3.2 从"未识别结构问题"显式转为"accepted gap"，按 D-series owner-撞点协议不再主动 hypothetical 推进。

---

## 1. §3.1 decline 理由（4 条）

1. **fixture harness 样本盲点**：35 realistic scenarios 中 9 次非 read-only approval 已能表达摩擦（D44 P1-A 修了 4 次 read-only bypass）；剩余 9 次是 D48 self-judged "设计权衡残余摩擦"，非真 bug
2. **trust mode 是工程性假设，无 owner 撞点验证**：D44 已 ship argv 运行时分类器 + `ALWAYS_READONLY` 集合；新增 trust 模式 = 加一层 state（per-owner trust level），但无数据证明 owner 真撞"误点 delete"
3. **扩 fixture 成本高于潜在价值**：35 场景 → 加 cascading approval fixtures ≈ 8-12 case；harness 时间 +30%；潜在价值 = 仅当 owner 真撞才显形
4. **D48 §3.1 自判**："**当前状态**：未识别。修选项 §18 没列入" — 笔记作者（D48 owner 视角）已判定非首要

---

## 2. §3.2 decline 理由（4 条）

1. **temperature model 实证**：v8 PRD candidate A/B/C 3/3 REVERT，原因 = temperature model 单 round 验证不可靠；D47 fixture-recording 同源风险未解除
2. **multi-round + prompt freeze 成本**：4 min × N round（N ≥ 5 才稳定 baseline），单次 fixture 校准 ≈ 20-30 min；35 场景全跑 ≈ 12-17 h（不可持续）
3. **方法论限制 ≠ 工程问题**：LLM 输出概率性是 fundamental；唯一可量化路径 = 多 round + 大样本统计，本质是 research 而非 product feature
4. **D48 §3.2 自判**："**当前状态**：未识别为'方法论限制'，列为'v8 candidate 待做'。D47 延续同源风险" — 已承认方法论限制

---

## 3. DESIGN.md 集成位置

| § | 行号 | 改动 |
|---|---|---|
| §18 | line 815-816 | +2 row (信任模式 + LLM 质量量化) |
| §11.4 | line 572 | +1 row (LLM 质量量化方法论基础设施) |

引用：[`../../DESIGN.md`](../../DESIGN.md)（从 `docs/superpowers/notes/` 上溯两级）

---

## 4. D48 doc status flip

| § | 原状态 | D51 后状态 |
|---|---|---|
| §3.1 line 83 | 未识别 | decline (2026-09-09 D51, handoff doc) |
| §3.2 line 92 | 未识别 / v8 candidate 待做 | decline (2026-09-09 D51, handoff doc) |
| §6 触发表 line 176 | ⬜ 等触发 | × declined (D51) |
| §6 触发表 line 177 | ⬜ 等触发 | × declined (D51) |

引用：[`./2026-09-08-d48-owner-perspective.md`](./2026-09-08-d48-owner-perspective.md)

---

## 5. Verification gate

- [ ] DESIGN.md §18 行 815-816 含 "declined, 2026-09-09 D51" × 2
- [ ] DESIGN.md §11.4 行 572 含 "declined, 2026-09-09 D51"
- [ ] D48 doc §3.1 行 83 含 "decline (2026-09-09 D51"
- [ ] D48 doc §3.2 行 92 含 "decline (2026-09-09 D51"
- [ ] D48 doc §6 触发表 行 176-177 含 "× declined (D51)" × 2
- [ ] 本 handoff doc 引用 DESIGN.md §18/§11.4 + D48 doc §3.1/§3.2/§6 行号与现 doc 一致
- [ ] git diff --stat 仅 DESIGN.md + D48 doc + handoff doc，无业务代码改动

---

## 6. Lessons

1. **fixture harness 样本盲点 ≠ 团队盲点**：D48 §3 三项结构 gap 暴露条件是 owner 真撞；不是 v5 wrap-around 团队的盲点，是 fixture harness 35 场景的样本盲点
2. **文档化 decline 是 closure 而非延后**：decline ≠ 移到 backlog；显式 "decline" + 引用 handoff doc = accepted gap，可审计
3. **D-series owner-撞点协议容许 doc-only closure**：D44/D46/D49 code ship；D51 doc-only closure 闭环；二者协议统一
4. **方法论限制 ≠ 可工程化**：§3.2 试图用 fixture harness 量化 LLM 输出本质不成立；正确路径是 owner 实测撞点 + 多 round methodology 固化，非产品代码

---

**End D51 handoff doc.**
