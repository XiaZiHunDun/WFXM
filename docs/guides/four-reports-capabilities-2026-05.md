# 四报告能力速查（2026-05）

> **状态**：主线 A–D + 支撑线 E（P2 子集）**已落地**  
> **路线图**：[`../plans/four-reports-improvement-roadmap-2026-05.md`](../plans/four-reports-improvement-roadmap-2026-05.md) §9  
> **明确不做**：[`../plans/four-reports-out-of-scope-2026-05.md`](../plans/four-reports-out-of-scope-2026-05.md)（新增需求前必读）  
> **架构表**：[`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)「四报告增量」节

本文是运维/开发用的**单一速查**，不替代四份对照报告全文。

---

## 1. 能力地图

| 主线 | 能力 | 主要模块 |
|------|------|----------|
| **A 检索** | 空召回 fallback、`butler memory search --verbose`、Markdown 切块、结构化引用、启发式子 query | `semantic_index.py`、`chunking.py`、`reindex.py`、`query_decompose.py`、`rag_diagnostics.py` |
| **B Loop 减熵** | 软循环 nudge、75% 预算预警、压缩 `IN-PROGRESS`、`inject_once` spill、破坏性工具后 batch stale | `tool_guardrails.py`、`loop_budget_nudge.py`、`compaction_prompt.py`、`tool_result_storage.py`、`batch_sequence_guard.py` |
| **C DESIGN** | `DESIGN.md` 节提取、post-compact 回灌、`design_preset`、`ui-build` 委派、`ui-dev-qa-loop` | `design_md_sections.py`、`handoff.py`、`post_compact_cleanup.py` |
| **D 实验** | `software-research` 模板、harness 只读、`experiments.tsv`、`METRIC` 协议、CLI | `butler/experiments/*`、`cli/experiment_cli.py` |
| **E 支撑** | workflow∩工具列表、`tool_modes`、隐式参数、schema 预优化、token 粗算 | `tool_implicit_context.py`、`schema_optimizer.py`、`token_cost_diagnostics.py` |

---

## 2. 常用环境变量

详见 [`../config/reference.md`](../config/reference.md) 与 [`.env.example`](../../.env.example)。

| 变量 | 用途 |
|------|------|
| `BUTLER_RAG_SUBQUERY` | 复合问句拆多路检索（启发式，非 LLM） |
| `BUTLER_EXPERIMENT_MODE` | 研究模式：harness 只读、`experiments/` 可写 |
| `BUTLER_EXPERIMENT_GIT_RESET` | 默认 `0`；`experiment discard --apply-reset` 才 reset |
| `BUTLER_TOOL_IMPLICIT_CONTEXT` | 工具调用隐式上下文注入 |
| `BUTLER_SCHEMA_OPTIMIZE` | API 前 schema 精简 |
| `BUTLER_TOKEN_COST_ESTIMATE` | `/诊断` 粗算 token 成本 |

DESIGN / Loop / RAG 其余变量与 CC 线束共用（如 `BUTLER_TOOL_RESULT_SPILL`、`BUTLER_DISABLE_AUTO_COMPACT`）。

---

## 3. CLI 与项目约定

```bash
# 检索调试（主线 A）
butler memory search "关键词" --project <名> --verbose

# 实验账本（主线 D）
butler experiment list --project <名>
butler experiment record --project <名> --name trial1 --metric loss=0.42
butler experiment best --project <名> --metric loss --minimize
butler experiment discard --project <名> --name trial1 --apply-reset   # 可选 git reset
```

**UI 项目**：根目录或 `.butler/design/DESIGN.md`；`project.yaml` 可选 `design_preset`。  
**设计 Skill 种子**：租户级 `tenants/<id>/skills/design-system.md`（非自动复制到每个项目 `.butler/skills/`）。  
**研究模板**：`software-research` archetype → `.butler/harness/` + `experiments/` + 可选 `PROGRAM.md`。

---

## 4. 测试守门

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest tests/test_design_md_sections.py tests/test_experiment_ledger.py \
  tests/test_query_decompose.py tests/test_support_line_e.py tests/test_roadmap_remainder.py \
  tests/test_ragflow_p0_retrieval.py tests/test_markdown_chunking.py tests/test_loop_pr2_entropy.py -q
```

改 `butler/memory/`、`butler/core/design_md_sections.py`、`butler/experiments/` 时至少跑上表；改 Gateway 仍用 [`CONTRIBUTING.md`](../../CONTRIBUTING.md) 语料门禁。

---

## 5. 已知限制（勿当 bug 重复修）

| 现象 | 说明 |
|------|------|
| `rag_last_*` 单槽 | 同轮 experience 与 project 预取可能互相覆盖 |
| reindex + chunking | `indexed_project_bullets` 可能为 0（按块索引） |
| 子 query | 启发式拆分；**不做** LLM 子 query（见 out-of-scope） |
| 73 套 DESIGN 标本 | **不进**主仓库；用项目自有 `DESIGN.md` + `design_preset` |

---

## 6. 文档索引

| 文档 | 说明 |
|------|------|
| [`four-reports-improvement-roadmap-2026-05.md`](../plans/four-reports-improvement-roadmap-2026-05.md) | PR1–PR6 与 §9 核对表 |
| [`four-reports-out-of-scope-2026-05.md`](../plans/four-reports-out-of-scope-2026-05.md) | 18 项否决能力 |
| [`awesome-design-md-butler-comparison-report-2026-05.md`](../plans/awesome-design-md-butler-comparison-report-2026-05.md) | DESIGN 对照全文 |
| [`ragflow-butler-comparison-report-2026-05.md`](../plans/ragflow-butler-comparison-report-2026-05.md) | RAG 对照全文 |
| [`autoresearch-butler-comparison-report-2026-05.md`](../plans/autoresearch-butler-comparison-report-2026-05.md) | 实验对照全文 |
| [`browser-use-butler-comparison-report-2026-05.md`](../plans/browser-use-butler-comparison-report-2026-05.md) | Loop 减熵对照全文 |
