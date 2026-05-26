# 五报告能力速查（2026-05）

> **状态**：主线 F–J + PR-F1–F6 + **P5–P10 子集** **已落地**（2026-05-25）  
> **路线图**：[`../plans/five-reports-improvement-roadmap-2026-05.md`](../plans/roadmaps/five-reports-improvement-roadmap-2026-05.md) §9  
> **前置**：[`four-reports-capabilities-2026-05.md`](four-reports-capabilities-2026-05.md)（四报告已收口）  
> **明确不做**：[`../plans/four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md) §7、路线图 §6 S1–S11

---

## 1. 能力地图

| 主线 | 能力 | 主要模块 |
|------|------|----------|
| **F 记忆** | `<private>`、三层 `butler_recall`、观察者队列、PreRead、session_summary | `private_tags.py`、`recall_layers.py`、`observer_queue.py`、`preread_context.py` |
| **G 运维** | 熔断/failover、`sessions list`、`/会话`、流式探活、用量盘、原子写 | `provider_health.py`、`sessions_cli.py`、`usage_ledger.py`、`stream_probe.py`、`io/atomic_write.py` |
| **H Prompt** | 任务纪律、RAG 忠实度、工具错误格式、Reflexion、规划 Generated Knowledge | `butler_system.md`、`tool_error_policy.py`、`reflexion_ephemeral.py` |
| **I 编排** | outcomes.tsv、`/评价`、handoff 依赖、clear_child、output_schema、决策解析 | `outcomes.py`、`task_orchestrator.py`、`report.py` |
| **J 可靠性** | retry/replan/stop、param blacklist、UTF-16 截断、Pipeline 步骤耗时 | `tool_error_policy.py`、`text_truncate.py`、`pipeline_steps.py`、`context_pipeline.py` |

**否决 / 边界**：见 [`../plans/five-reports-not-done-2026-05.md`](../plans/decisions/five-reports-not-done-2026-05.md)（S1–S11；超出 P5–P10 子集的能力勿重复立项）。

---

## 2. 微信命令

| 命令 | 说明 |
|------|------|
| `/评价` / `/outcome` | outcome log：list / resolve pending |
| `/会话` / `/sessions` | 最近 transcript 会话列表 |
| `/诊断` | 含 ContextPipeline 步骤 ms、用量盘、stream probe（若开启） |
| `/预设` | 列出 `butler://` provider 预设 |
| `/模型 preset …` | 应用预设到项目或 runtime（见 P8） |

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

# P5–P10 子集
butler mcp sync [--workspace PATH]
butler mcp scan <server_id>
butler skills sync
butler prompt eval [--corpus] [--llm]
butler provider presets | butler provider apply <id> --workspace PATH
butler registry verify
butler sessions layered <session_key>   # BUTLER_POST_SESSION_LAYERED=1
```

---

## 4. P5–P10 子集（2026-05）

| 批次 | 能力 |
|------|------|
| P5 | MCP/Skills SSOT、`BUTLER_TOOLS_ENGINE`、reflexion write |
| P6 | `prompt eval`、post_session layered、injection LLM、provider presets |
| P7 | 安装前扫描、`BUTLER_INJECTION_LLM_GATE` |
| P8 | `provider apply`、`/模型 preset` |
| P9 | LLM rubric、corpus live smoke、ToolsEngine SSOT |
| P10 | thinking beta 头、`registry verify`、corpus live full、schema 多轮 repair、`trading-debate` workflow |

详见 [`external-agent-reports-capabilities-2026-05.md`](external-agent-reports-capabilities-2026-05.md)。

---

## 5. 常用环境变量

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

## 6. 测试守门

```bash
cd /home/ailearn/projects/WFXM

# PR-F1–F6
PYTHONPATH=. pytest tests/test_lobehub_p0_features.py tests/test_peg_prompt_contracts.py \
  tests/test_memory_recall_layers.py tests/test_provider_health.py tests/test_sessions_cli.py \
  tests/test_outcome_reflection.py tests/test_task_orchestrator_handoff.py \
  tests/test_five_reports_f6.py -q

# P5–P10 一条命令
./scripts/butler-five-reports-gate.sh
```

---

## 7. 否决清单（索引）

| 类型 | 文档 |
|------|------|
| 五报告否决与边界 | [`../plans/five-reports-not-done-2026-05.md`](../plans/decisions/five-reports-not-done-2026-05.md) |
| 四报告 18 项否决 | [`../plans/four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md) §2 |
