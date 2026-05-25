# 五报告能力速查（2026-05）

> **状态**：主线 F–J + PR-F1–F6 **已落地**（2026-05-25）  
> **路线图**：[`../plans/five-reports-improvement-roadmap-2026-05.md`](../plans/five-reports-improvement-roadmap-2026-05.md) §9  
> **前置**：[`four-reports-capabilities-2026-05.md`](four-reports-capabilities-2026-05.md)（四报告已收口）  
> **明确不做**：[`../plans/four-reports-out-of-scope-2026-05.md`](../plans/four-reports-out-of-scope-2026-05.md) §7、路线图 §6 S1–S11

---

## 1. 能力地图

| 主线 | 能力 | 主要模块 |
|------|------|----------|
| **F 记忆** | `<private>`、三层 `butler_recall`、观察者队列、PreRead、session_summary | `private_tags.py`、`recall_layers.py`、`observer_queue.py`、`preread_context.py` |
| **G 运维** | 熔断/failover、`sessions list`、`/会话`、流式探活、用量盘、原子写 | `provider_health.py`、`sessions_cli.py`、`usage_ledger.py`、`stream_probe.py`、`io/atomic_write.py` |
| **H Prompt** | 任务纪律、RAG 忠实度、工具错误格式、Reflexion、规划 Generated Knowledge | `butler_system.md`、`tool_error_policy.py`、`reflexion_ephemeral.py` |
| **I 编排** | outcomes.tsv、`/评价`、handoff 依赖、clear_child、output_schema、决策解析 | `outcomes.py`、`task_orchestrator.py`、`report.py` |
| **J 可靠性** | retry/replan/stop、param blacklist、UTF-16 截断、Pipeline 步骤耗时 | `tool_error_policy.py`、`text_truncate.py`、`pipeline_steps.py`、`context_pipeline.py` |

**仍不做（P2 大项）**：CC Switch 桌面、MCP Host 全家桶、LangGraph 行情图、Chroma Worker 等 — 见路线图 §6。

---

## 2. 微信命令

| 命令 | 说明 |
|------|------|
| `/评价` / `/outcome` | outcome log：list / resolve pending |
| `/会话` / `/sessions` | 最近 transcript 会话列表 |
| `/诊断` | 含 ContextPipeline 步骤 ms、用量盘、stream probe（若开启） |

---

## 3. CLI

```bash
# 会话（主线 G）
butler sessions list [--search TEXT] [--limit N]

# 实验 outcome（主线 I）
butler experiment outcome list --project <名>
butler experiment outcome resolve --project <名> --row-id <id> --value <结果> [--reflection "..."]

# 三层 recall（主线 F，需 BUTLER_MEMORY_RECALL_LAYERS=1）
# 工具 butler_recall mode=index|fetch|timeline
```

---

## 4. 常用环境变量

详见 [`../config/reference.md`](../config/reference.md)。

| 变量 | 默认 | 用途 |
|------|------|------|
| `BUTLER_MEMORY_OBSERVER_QUEUE` | 0 | PostToolUse → `.butler/observations.tsv` |
| `BUTLER_MEMORY_PREREAD` | 1 | 读文件前注入路径历史摘要 |
| `BUTLER_SESSION_SUMMARY` | 1 | Stop 写 `.butler/session_summary.json` |
| `BUTLER_OUTCOME_REFLECTION` | 1 | outcomes.tsv + orchestrator 注入 |
| `BUTLER_WORKFLOW_HANDOFF_ONLY` | 1 | DAG 依赖默认 Handoff 块 |
| `BUTLER_WORKFLOW_CLEAR_CHILD` | 0 | 节点后清子 transcript |
| `BUTLER_STREAM_PROBE` | 0 | `/诊断` 最小 complete 探活 |
| `BUTLER_USAGE_PERSIST` | 1 | 用量 JSONL |
| `BUTLER_REFLEXION_EPHEMERAL` | 0 | 连续工具失败 ephemeral 反思 |
| `BUTLER_ADVERSARIAL_MARK` | 1 | 入站 injection 模式前缀标记 |
| `BUTLER_PREFETCH_INJECTION_FILTER` | 1 | 预取记忆行过滤 injection |

---

## 5. 测试守门

```bash
cd /home/ailearn/projects/WFXM

PYTHONPATH=. pytest tests/test_lobehub_p0_features.py tests/test_peg_prompt_contracts.py \
  tests/test_memory_recall_layers.py tests/test_provider_health.py tests/test_sessions_cli.py \
  tests/test_outcome_reflection.py tests/test_task_orchestrator_handoff.py \
  tests/test_five_reports_f6.py -q

# 四报告 + CC 回归
PYTHONPATH=. pytest tests/test_ragflow_p0_retrieval.py tests/test_design_md_sections.py \
  tests/test_experiment_ledger.py tests/test_tool_result_storage.py tests/test_message_queue.py -q
```
