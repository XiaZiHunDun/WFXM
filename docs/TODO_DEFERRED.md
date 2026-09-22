# Butler v5 — TODO / Deferred Items Inventory

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計) | **读者**: Owner / Contributor / D-series 启动者
> **关系**:
> - 功能清单（含 §8 deferral 状态）→ [`FEATURES.md`](FEATURES.md) §8
> - 目标架构（§18 延后项 anchor）→ [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §18
> - 测试覆盖（PRE-EXISTING）→ [`TESTS.md`](TESTS.md) §9
> - D53b TODO 实证 → [`../butler-v5/tools/todo-inventory.md`](../butler-v5/tools/todo-inventory.md)（2026-09-11）
> - D53c deferral reeval → [`../docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md`](../docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md)（如存在）
> - D51 decline gaps → DESIGN §18 line 825-826 + D51 cycle memos

> **范围**: 本表覆盖**全部 deferral 维度**（in-code TODO / DESIGN §18 / D51 declined / V8 PRD / cycle carry）；**不**只看在-code TODO 标记（D53b 已实证 0 active TODO）。

---

## 图例

- ✅ **已 ship**（不应在本表）
- 📅 **DEFERRED**（DESIGN §18 trigger-条件未达；D53c reeval 0 新 evidence）
- ❌ **DECLINED**（D51 实证 不可行 / 价值低于成本；保留记录但不启）
- ⏸ **CYCLE CARRY**（D-series 撞出但下 batch 没修；保留原因）
- 🔬 **RESOURCE EXHAUSTED**（v8 PRD A/B/C 3/3 revert；候选 D 等 owner hand-trial）

## §0 总览

| 维度 | 数量 | Source |
|------|------|--------|
| §1 In-code TODO markers | **0** active | D53b `tools/todo-inventory.md` (2026-09-11) |
| §2 DESIGN §18 deferred items | **13** | DESIGN §18 + D53c reeval |
| §3 Declined items (D51) | **2** | D51 §5.4 + DESIGN §18 line 825-826 |
| §4 V8 PRD candidates | **4** | `docs/plans/active/v5-real-llm-v8-iteration-2026-09.md` |
| §5 D-series cycle carry | **~6** lessons | per cycle memos |
| **Total tracked** | **~25** | — |

## §1 In-code TODO markers（D53b 实证 0 active）

> D53b (2026-09-11) 全仓 grep `TODO\|FIXME\|XXX\|HACK` → 35 raw matches；全部为 false positive / infrastructure / planning doc references。

| File | Marker | Class | 共识 |
|------|--------|-------|------|
| _(none — production code clean)_ | — | — | ✅ 健康状态 |
| `apps/api/src/tools.ts:498` | `TODO` (in string literal) | false positive | keep（example usage `"rg", "TODO", "src"`） |
| `docs/superpowers/specs/*.md` | `TODO` (in 3 files) | infrastructure | keep（design spec 引用） |
| `docs/superpowers/plans/*.md` | `TODO` (in 2 files) | infrastructure | keep（plan 引用） |
| `scripts/cutover/*` | `TODOIST_API_TOKEN` (env var name) | false positive | keep（env var literal） |
| `tests/.../recordings-archive/*.json` | `TODO` (in 2 files) | archived body text | gitignored（D45 engineering-hygiene） |

**New TODOs policy**: 未来 ship batch 若引入 TODO marker（in `.ts` 或非 planning `.md`），必须更新 `todo-inventory.md` + D# tracking；D53c 提议 `pnpm todo:check` CI gate（未实施）。

## §2 DESIGN §18 Deferred Items（trigger-conditioned, 13 项）

> DESIGN §18 硬规则：**没有触发证据时，不进入路线图**（line 830）。D53c reeval (2026-09-11)：**0 新 evidence, 状态保持**。

| 项 | 触发条件 | 当前状态 | Source 指针 |
|----|----------|----------|-------------|
| **独立 approvals 表** | 当前 `waiting_approval` Step 字段承载够用 | 📅 not trigger | DESIGN §11.4 + §18 |
| **独立 memory_records 表** | Durable Memory 走 §12 `durable_memories` 足够 | 📅 not trigger | DESIGN §18 |
| **全量 Projection / 独立读库** | owner 实测查询延迟超预算（41/41 pass） | 📅 not trigger | DESIGN §11.4 |
| **Snapshot + DeltaChannel** | 运行历史 p95 超预算；D53a snapshot 是 test artifact 非 prod API | 📅 not trigger | DESIGN §11.4 |
| **Command Bus / Query Bus** | owner 实测同步耦合严重 | 📅 not trigger | DESIGN §11.4 |
| **通用 Event Bus** | DESIGN §7 line 60 explicit 默认直调 | 📅 not trigger | DESIGN §11.4 |
| **Kafka / Redis Stream / 独立 Broker** | 单进程故障隔离实测不足 | 📅 not trigger | DESIGN §11.4 |
| **Telegram Channel 完整化** | wechat + slack 已承载；telegram 无触发 | 📅 not trigger | DESIGN §18 |
| **浏览器 UI (第二 Loop)** | DESIGN §7.1 条件准入 | 📅 半 trigger (R16 partial) | DESIGN §7.1 |
| **外部 OTEL exporter** | 本地 trace 无法定位生产问题 | 📅 not trigger | DESIGN §18 |
| **独立 worker 进程** | 同进程 Outbox worker 资源隔离不足 | 📅 not trigger | DESIGN §18 |
| **Task 聚合**（独立任务板） | 已 trigger (D22) + D53c 0 新 evidence | ✅ not relevant (已 ship) | DESIGN §18 line 814 |
| **Procedure 模板**（DAG） | 已 trigger (D22) + D53c 0 新 evidence | ✅ not relevant (已 ship) | DESIGN §18 line 815 |

**§18 row 3 治理链路 (G3+G1+G2+G4+G5)** = D39-D43 全 ship ✅，无留待项；详见 FEATURES §3。

## §3 Declined Items（D51 + D53c，2 项）

> D51 (2026-09-09) 实证不可行 / 价值低于成本；D53c (2026-09-11) reeval 状态保持 declined。

| 项 | 失败原因 | Decline source | 替代方案 |
|----|---------|----------------|----------|
| **LLM 输出质量量化**（multi-round + prompt freeze baseline） | temperature model 单 round snapshot 不可靠；multi-round methodology 4min × N round 成本；扩 fixture 价值低于成本 | D51 + D53c；DESIGN §18 line 826 | fixture harness 41 场景已能表达产品层；待 owner 实测撞"B 类某场景答错"且能固化 multi-round methodology 才重评估 |
| **Approval trust mode**（高频 Approval 触发降低 owner 警觉） | fixture harness 样本盲点；35 场景 9 次非 read-only approval 已能表达摩擦；扩 fixture 成本 > 价值 | D51 + D53c；DESIGN §18 line 825 | D44 P0 inline-approval（`y` / `👌` / `✅` / `👍` 真实 resume）已修相邻痛点 |

## §4 V8 PRD Candidates（4 项）

> `docs/plans/active/v5-real-llm-v8-iteration-2026-09.md`（resource exhausted）

| 项 | 状态 | 说明 | Source |
|----|------|------|--------|
| **候选 A** — Fixture 校准（A5/C8/D3/D5 expect 调整） | 🔬 resource exhausted | 2026-09-07 实证 revert：aggregate 退化 88%→78% / 178s→224s；whack-a-mole | `feedback-template-feedback-naming-2026-09-07` |
| **候选 B** — Convergence prompt 加固（missing-context ask） | 🔬 resource exhausted | 2026-09-07 实证 revert：与 P2 take-action bias 互斥；aggregate 退化 88%→69% / 178s→261s / A2 单 case 11s→54s | `feedback-over-clarification-prompt-tradeoff-2026-09-07` |
| **候选 C** — Read-only bypass 扩 wsat | 🔬 resource exhausted | 2026-09-07 实证 revert：扩 `tree` 后 aggregate 退化 88%→75% / 178s→262s；35 场景中 tree 0 次使用；model variance 主导 | `feedback-temperature-model-changes-unprovable-2026-09-07` |
| **候选 D** — Owner hand-trial 反馈循环 | ⏸ cycle carry（无主动代码改动） | 等 owner 手试 1 周 → 撞真问题 → 触发下批 PRD | `v5-real-llm-v8-iteration-2026-09.md` |

**Temperature model 单 round 验证不可靠**：35 scenario 单一 snapshot 不能区分 fix 改对了 vs model variance。需 N round avg metrics 或 owner hand-trial 真问题触发。

**Rotation policy 锚定**（v7-current README 引用）：每 v8+ candidate 实施前需：
1. Snapshot current → `recordings-archive/v8-pre-{name}-fix`
2. Apply + re-record 35 scenarios
3. Diff vs v7 baseline
4. Aggregate metrics gate（decision match ≥28/32, latency ≤196s, no regression）

## §5 D-series Cycle Carry（~6 lessons）

> D-series 26 cycles 撞出的 lessons / carries；D50 lesson — ship claim 用 last batch green 不可信，必须 fresh full verify。

| Lesson | 来源 | Carry reason | 触发 |
|--------|------|--------------|------|
| **Ship claim fresh full verify** | D50 (2026-09-09) | last batch green 不可信；下一个 batch 必须 fresh full | 永久方法学 |
| **F1 fatigue scenario 加 scenario C** | D64 T5 (2026-09-14) | F1 acceptance 加 scenariosC；41→42 | 已 ship |
| **Fatigue signal populate 4th cycle** | D74 T3 (2026-09-20) | 4th cycle carry，闭环 |
| **Recording-baseline fixture v8 partial stale** | v7-current → v8 baseline 未建 | 候选 A/B/C 3/3 revert；待 owner hand-trial | 触发 D80 真-LLM batch |
| **F1/F2/F3 acceptance gap documentation** | D64 T5 (2026-09-14) | F1 flow smoke + F2 sensitive checklist + F3 chat-side 探针；3 gaps documented in §5.4 spec | 已 ship |
| **C-O-* note 4th cycle update** | D73 T4 (2026-09-20) | audit emit actor 改 reply 字符串必须同 batch 改测试（G-7 角色分离） | 永久方法学 |

## §6 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单（含 §8 deferral 状态） | [`FEATURES.md`](FEATURES.md) §8 |
| API endpoint | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| env vars | [`ENV.md`](ENV.md) |
| 测试覆盖（含 PRE-EXISTING） | [`TESTS.md`](TESTS.md) §9 |
| DESIGN §18 延后项 anchor | [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §18 |
| D53b TODO 实证 | [`../butler-v5/tools/todo-inventory.md`](../butler-v5/tools/todo-inventory.md) |
| D53c deferral reeval | `docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md`（如存在） |
| V8 PRD | [`plans/active/v5-real-llm-v8-iteration-2026-09.md`](plans/active/v5-real-llm-v8-iteration-2026-09.md) |
| D-series 累计 + 维度候选 | [`ROADMAP.md`](ROADMAP.md) |

---

**End of TODO_DEFERRED.md** | D80 cycle 26 inventory batch | **~25 deferred items / 5 categories**（in-code TODO 0 / DESIGN §18 13 / declined 2 / V8 PRD 4 / cycle carry 6）