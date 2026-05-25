# 外部 Agent 五报告能力速查（2026-05）

> **状态**：PR-X1–X6 + 主线 M 后续子集 **已落地**  
> **路线图**：[`../plans/external-agent-reports-improvement-roadmap-2026-05.md`](../plans/external-agent-reports-improvement-roadmap-2026-05.md) §10  
> **未作 / 否决**：[`../plans/five-reports-not-done-2026-05.md`](../plans/five-reports-not-done-2026-05.md)

---

## 1. 能力地图

| 主线 | 能力 | 模块 / 开关 |
|------|------|-------------|
| **K** | Message IR、tool_wire、入站序列校验 | `message_ir.py`、`tool_wire.py`、`inbound_validate.py` |
| **K** | prompt_renderer、project `plugins:` | `prompt_renderer.py`、`project_plugins.py` |
| **L** | skill rescue、safety finish、MCP deferred、ask_clarification | `context_pipeline.py`、`mcp/deferred.py` |
| **L** | static system-reminder、LoopMiddleware | `system_reminder.py`、`loop_middleware.py` |
| **M** | 两阶段确认、STUCK、风险 ask | `two_phase_confirm.py`、`loop_stuck.py` |
| **M** | session initializing 入队 | `session_lifecycle.py` |
| **N** | exp_cache、BM25 recall、schema 校验/修复 | `exp_cache.py`、`tool_recall_bm25.py`、`report.py` |
| **N** | PlanSnapshot、QA FAIL replan | `plan_snapshot.py`、`workflows/runner.py` |
| **O** | rescue/optional、checkpoint、handlers、until | `workflows/schema.py`、`callbacks.py` |

---

## 2. 常用环境变量（默认关的需显式开启）

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_TWO_PHASE_CONFIRM` | 0 | 高风险工具两阶段确认 |
| `BUTLER_PERMISSION_RISK_HEURISTIC` | 0 | 终端危险模式改 ask |
| `BUTLER_MCP_DEFERRED_TOOLS` | 0 | MCP 延迟 schema |
| `BUTLER_STATIC_SYSTEM_REMINDER` | 0 | 静态 system + user reminder |
| `BUTLER_EXP_CACHE` | 0 | LLM 经验缓存 |
| `BUTLER_TOOL_RECALL_BM25` | 0 | BM25 工具召回 |
| `BUTLER_MESSAGE_IR` | 1 | 入站 canonical IR |
| `BUTLER_TOOL_WIRE` | 1 | 厂商 tool 线适配 |
| `BUTLER_WORKFLOW_RESCUE` | 1 | rescue_steps |
| `BUTLER_WORKFLOW_OPTIONAL` | 1 | optional 依赖 |
| `BUTLER_GATEWAY_SESSION_INITIALIZING` | 1 | 首条会话冷启动入队 |
| `BUTLER_WORKFLOW_QA_REPLAN` | 1 | dev-qa-loop QA FAIL 重跑 implement |
| `BUTLER_WORKFLOW_QA_REPLAN_MAX` | 1 | 重跑次数上限 |

完整表见 [`../config/reference.md`](../config/reference.md)。

---

## 3. project.yaml `plugins:` 示例

```yaml
plugins:
  BUTLER_EXP_CACHE: "1"
  BUTLER_MCP_DEFERRED_TOOLS: "0"
```

进程内 **已有** 的 `BUTLER_*` 环境变量优先，yaml 仅补未设置的键。

---

## 4. 测试守门

```bash
cd /home/ailearn/projects/WFXM

PYTHONPATH=. pytest tests/test_external_agent_*.py tests/test_message_ir.py \
  tests/test_mcp_deferred.py tests/test_gateway_handler.py -q
```

---

## 5. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：PR-X3–X6 + M 后续 + P1–P4 深化速查 |
