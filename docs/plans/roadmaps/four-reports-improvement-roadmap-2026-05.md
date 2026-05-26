# 四份报告合并改进路线图（2026-05）

> **状态**：**已收口**（2026-05-25）；主线 A–D + 支撑线 E 已落地（见 §9）；运维速查 [`../guides/four-reports-capabilities-2026-05.md`](../../guides/four-reports-capabilities-2026-05.md)；**明确不做**见 §7 与 [`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md)  
> **来源**：[`awesome-design-md-butler-comparison-report-2026-05.md`](awesome-design-md-butler-comparison-report-2026-05.md)、[`autoresearch-butler-comparison-report-2026-05.md`](autoresearch-butler-comparison-report-2026-05.md)、[`browser-use-butler-comparison-report-2026-05.md`](browser-use-butler-comparison-report-2026-05.md)、[`ragflow-butler-comparison-report-2026-05.md`](ragflow-butler-comparison-report-2026-05.md)  
> **事实基线**：[`../architecture/v4-architecture.md`](../../architecture/v4-architecture.md) 与 `butler/` 当前实现  
> **原则**：零新增重依赖；不改变 Butler「微信管家 + 多项目开发 Agent」产品边界

---

## 1. 这份文档解决什么问题

四份报告分别讨论了：

- `awesome-design-md`：`DESIGN.md` 视觉上下文
- `autoresearch`：实验组织、账本、keep/discard
- `browser-use`：Loop 减熵、预算、一次性注入
- `RAGFlow`：检索质量、切块、引用、诊断

它们彼此正交，但都指向同一个问题：**Butler 已有强 Loop 与工具系统，下一步该把“上下文、检索、收尾、自我改进”做得更稳。**

本路线图将四份报告收敛为 **4 条主线 + 1 条支撑线**，用于后续拆 PR 与排期。

---

## 2. 总体判断

### 应优先增强的，不是新平台

应做：

1. **更会找**：检索 fallback、层级切块、结构化引用
2. **更会停**：软循环提示、预算预警、大结果只注入一轮
3. **更会做 UI**：`DESIGN.md` 上下文管线
4. **更会做实验**：harness 边界、实验账本、指标协议

不做：

- 内嵌 browser-use 式 CDP / DOM / 截图流水线
- 嵌入 RAGFlow 全栈（ES/Infinity/MinIO/Studio）
- 把 73 套 `DESIGN.md` 标本打入主仓库
- 在默认微信路径中启用 autoresearch 式通宵自治、自动 reset

---

## 3. 主线与优先级

### 主线 A — 检索增强（最高优先级）

**目标**：先把 Butler 的 RAG 做得更稳、更可解释。

| 优先级 | 项 | 产出 |
|--------|----|------|
| **P0** | 空召回 fallback | 首轮无结果时放宽阈值 / 扩大 limit / 仅 FTS 再试一轮 |
| **P0** | `/诊断` 检索增强 | 展示 fallback 次数、候选数、hybrid 权重、检索模式 |
| **P0** | CLI verbose 检索调试 | `butler memory search --verbose` |
| **P1** | Markdown 层级切块 | 长架构文档 / `DESIGN.md` / README 以标题树切块 |
| **P1** | 结构化引用 | `chunk_id`、`source_path`、`score_breakdown` |
| **P1** | 字段加权 / 子 query | 标题、关键字加权；必要时多子 query |

**主要落点**：

- `butler/memory/semantic_index.py`
- `butler/memory/reindex.py`
- `butler/memory/chunking.py`
- `butler/tools/knowledge_search.py`
- `butler/ops/rag_diagnostics.py`
- `butler/main.py`

**为什么先做**：这条线同时服务 `MEMORY.md`、项目知识、长架构文档、未来 `DESIGN.md`，复用现有 `semantic_index`，收益最大。

---

### 主线 B — Loop 减熵

**目标**：减少空转、误结束、重复上下文污染。

| 优先级 | 项 | 产出 |
|--------|----|------|
| **P0** | 软循环提示 | 在硬 `doom_loop` 之前先注入短 nudge |
| **P0** | 75% 预算预警 | 接近 `max_iterations` 或预算阈值时提示收尾 |
| **P0** | Compaction 未完成态约束 | 压缩提示词要求把未完成项标为 `IN-PROGRESS` |
| **P1** | `inject_once` spill | 大结果只在下一轮完整注入，后续只保留指针+摘要 |
| **P1** | 破坏性工具后截断同批后续动作 | `patch` / `write_file` 后使同批 stale read 失效 |

**主要落点**：

- `butler/tool_guardrails.py`
- `butler/core/tool_loop_detect.py`
- `butler/core/agent_loop.py`
- `butler/core/context_compressor.py`
- `butler/core/tool_result_storage.py`
- `butler/core/tool_prune_policy.py`
- `butler/core/tool_batch.py`
- `butler/core/parallel_tools.py`

**与现状关系**：不是替换现有硬 guardrail，而是在其前面补一层“软提示 + 收尾纪律”。

---

### 主线 C — DESIGN 上下文管线

**目标**：把 `DESIGN.md` 变成 Butler 的项目级一等公民，而不是做 UI 平台。

| 优先级 | 项 | 产出 |
|--------|----|------|
| **P0** | 项目约定 | UI 项目根目录支持 `DESIGN.md` |
| **P0** | QA / Handoff 视觉验收 | review 要核对 Do's / Don'ts、responsive、token |
| **P1** | `design_md_sections` | 提取 frontmatter 摘要、Do's / Don'ts、Responsive Behavior |
| **P1** | `design-system` skill | UI 任务先读 `DESIGN.md`，再按 token 迭代 |
| **P1** | `ui-build` 委派类别 | prompt_append 与 Handoff 视觉验收 |
| **P1** | `project.yaml` `design_preset` | 指向项目内或参考 preset |

**主要落点**：

- `butler/core/design_md_sections.py`
- `butler/orchestrator.py`
- `butler/core/post_compact_cleanup.py`
- `butler/core/handoff.py`
- `butler/workflows/builtin/dev-qa-loop.yaml`
- `delegate_categories.yaml`
- 项目级 `.butler/skills/` 或内置 skill

**边界**：

- 只做上下文与验收增强
- 不把 `reference/awesome-design-md/` 标本打入主仓库

---

### 主线 D — 实验组织（研究模式）

**目标**：把 autoresearch 的“可对比、可记账、可回滚实验协议”收为 Butler 的可选研究模式。

| 优先级 | 项 | 产出 |
|--------|----|------|
| **P1** | harness 边界 | `.butler/harness/` 只读；`experiments/` 可写 |
| **P1** | 实验账本 | `.butler/experiments.tsv` 或 JSONL |
| **P1** | 指标协议 | runtime 输出 `METRIC name=value` |
| **P1** | `/诊断` / CLI 最近实验摘要 | 查看 keep / discard / crash |
| **P2** | `BUTLER_EXPERIMENT_MODE` | 仅实验分支 + 仅实验面可写 |
| **P2** | 受控 keep/discard | 指标未改善时回到 best SHA（不进默认微信路径） |

**主要落点**：

- 项目模板 / archetype
- `.butler/permissions.yaml` 模板
- `runtime/jobs.yaml`
- `butler/ops/runtime_metrics.py`
- `butler/main.py`

**边界**：

- 不在默认微信 mutating 路径启用自动 reset
- 不在 main 分支做 autoresearch 式每轮提交

---

### 支撑线 E — Schema / 成本 / Tool 子集

**目标**：把系统做精，但优先级低于前四条主线。

| 优先级 | 项 | 产出 |
|--------|----|------|
| **P2** | 动态 tool 子集 | 按项目 / workflow step / mode 缩小暴露工具 |
| **P2** | special 参数统一注入 | `project_root`、`session_key` 等隐式依赖统一 |
| **P2** | schema optimizer | 降低结构化输出 400 错误 |
| **P2** | token / cost 估算 | `/诊断` 显示模型成本趋势 |

**主要落点**：

- `butler/tools/registry.py`
- `butler/permissions.py`
- `butler/execution_context.py`
- `butler/core/schema_recovery.py`
- `butler/ops/runtime_metrics.py`

---

## 4. P0 可执行清单

### P0-A：检索 fallback 与诊断

1. 在 `semantic_index` 增加 fallback 策略
2. 在 `knowledge_search` 返回结构化元信息
3. 在 `rag_diagnostics` 展示 fallback / 候选数 / 权重
4. 增 CLI `butler memory search --verbose`

**建议测试**：

```bash
PYTHONPATH=. pytest tests/test_sprint_bcd.py tests/test_runtime_metrics.py -q
```

新增建议：

```bash
PYTHONPATH=. pytest tests/test_ragflow_p0_retrieval.py -q
```

### P0-B：软循环提示与预算预警

1. 在 `tool_loop_detect` 增加 soft-nudge 结果
2. 在 `agent_loop` 注入 75% 预算提示
3. 在 compaction prompt 明确 `IN-PROGRESS`

**建议测试**：

```bash
PYTHONPATH=. pytest tests/ -k "guardrail or doom_loop or tool_batch" -q
```

### P0-C：DESIGN 约定与视觉验收

1. 文档约定：UI 项目可放 `DESIGN.md`
2. `dev-qa-loop` review 步骤补视觉核对项
3. Handoff 补充颜色、spacing、responsive 验收提示

**建议测试**：

```bash
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py -q
```

---

## 5. 建议 PR 顺序

为避免同时改动 Loop、RAG、workflow，建议拆为 6 个小 PR：

1. **PR1**：RAG fallback + `/诊断` 检索增强
2. **PR2**：soft nudge + 75% 预算预警 + compaction `IN-PROGRESS`
3. **PR3**：`inject_once` spill
4. **PR4**：Markdown 层级切块 + 结构化引用
5. **PR5**：`design_md_sections` + `design-system` + `ui-build`
6. **PR6**：实验模板 + `experiments.tsv` + runtime metric 协议

---

## 6. 与现有规划的关系

| 文档 | 关系 |
|------|------|
| [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) | 本文是其后续“能力增强”子路线图 |
| [`cc-butler-gap-analysis-2026-05.md`](../active/cc-butler-gap-analysis-2026-05.md) | 本文不替代 CC 线束，优先改增量能力 |
| [`awesome-design-md-butler-comparison-report-2026-05.md`](awesome-design-md-butler-comparison-report-2026-05.md) | 提供 DESIGN 主线来源 |
| [`autoresearch-butler-comparison-report-2026-05.md`](autoresearch-butler-comparison-report-2026-05.md) | 提供实验组织主线来源 |
| [`browser-use-butler-comparison-report-2026-05.md`](browser-use-butler-comparison-report-2026-05.md) | 提供 Loop 减熵主线来源 |
| [`ragflow-butler-comparison-report-2026-05.md`](ragflow-butler-comparison-report-2026-05.md) | 提供检索增强主线来源 |

---

## 7. 明确不做

> **完整清单（含原因、替代方案、来源报告）**：[`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md)  
> **合并索引（四报告 + 五报告 + defer + Backlog）**：[`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md)

摘要（18 项，详见 out-of-scope 文档 §2 总表）：

| 类别 | 不做 |
|------|------|
| 浏览器 / 视觉 | 内嵌 CDP、每步截图、Playwright 视觉农场、browser-use Cloud |
| RAG 平台 | RAGFlow 全栈、ES/MinIO/Studio、MinerU/Docling 全家桶 ingest |
| DESIGN 标本 | 73 套 DESIGN 进主仓、Stitch 商业流水线、`preview.html`、独立设计 Agent 运行时 |
| 实验自治 | 微信路径通宵 NEVER STOP、无门控每轮 commit、无门控自动 git reset |
| 架构越界 | 训练平台化、浏览器控制平台、LLM 辅助子 query（额外模型） |
| 可选仅 CI | `design.md lint` 不进默认 Loop |

**Butler 替代**：自建 hybrid 检索 + `chunking`；`web_fetch`/文本 QA；项目 `DESIGN.md` + `ui-build`；`software-research` harness + 账本 + CLI；启发式 `BUTLER_RAG_SUBQUERY`。

---

## 8. 一句话总结

这四份报告合并后的方向，不是“给 Butler 再加一套大系统”，而是把现有 Butler 补成：

- **更会找**：RAG fallback、层级切块、结构化引用
- **更会停**：软循环提示、预算预警、一次性注入
- **更会做 UI**：`DESIGN.md` 上下文管线
- **更会做实验**：harness、账本、指标协议

这是 Butler 从“会调工具”走向“会管理上下文、收尾与自我迭代”的下一阶段。

---

## 9. 落地核对表（2026-05）

| 项 | 状态 | 说明 |
|----|------|------|
| 主线 A P0–P1 | ✅ | fallback、诊断、CLI、`chunking`、结构化引用、heading_boost、启发式子 query |
| 主线 B P0–P1 | ✅ | soft nudge、75% 预算、IN-PROGRESS、inject_once、batch stale guard |
| 主线 C P0–P1 | ✅ | `design_md_sections`、`ui-build`、`design_preset`、skill 种子、`ui-dev-qa-loop`、plan_mode UI 节 |
| 主线 D P1–P2 | ✅ | harness/账本/METRIC/CLI/诊断、`EXPERIMENT_MODE`、discard+reset、crash 连续阻断、`PROGRAM.md` |
| 支撑线 E P2 | ✅ | workflow 工具交、`tool_modes`、隐式参数、schema 预优化、token 粗算 |
| 简洁性锚点 / 语料 DESIGN 路由 | ✅ | post-compact；`corpus_router` design_keywords |
| LLM 子 query | ⏭️ | 启发式已够用；见 [out-of-scope §2#15](../decisions/four-reports-out-of-scope-2026-05.md) |
| Stitch lint / Playwright / 通宵自治 / RAGFlow 全栈 等 | ⏭️ | 见 [out-of-scope](../decisions/four-reports-out-of-scope-2026-05.md) §2 |
