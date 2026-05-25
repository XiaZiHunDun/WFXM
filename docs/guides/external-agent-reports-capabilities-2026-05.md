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

## 5. 五报告 P2/P6/P7 子集（CLI）

```bash
butler mcp sync [--workspace PATH] [--dry-run] [--reload]
butler mcp scan <server_id>   # 安装前扫描（不写 mcp.yaml）
butler skills sync [--dry-run]
butler prompt eval            # pattern rubric，无需 API Key
butler prompt eval --corpus   # + corpus mock 子集（DA-32 等）
butler prompt eval --corpus-live   # overlay live 子集
butler prompt eval --corpus-live-smoke   # registry v2–v5 live_smoke_ids
butler prompt eval --corpus-live-full    # registry 单轮 live（BUTLER_PROMPT_EVAL_LIVE_MAX）
butler prompt eval --llm   # 辅助模型 rubric（BUTLER_PROMPT_EVAL_LLM=1）
butler registry verify
butler sessions layered <session_key>   # BUTLER_POST_SESSION_LAYERED=1
# 微信: /预设  /模型 preset …
# workflow 模板: trading-debate（builtin）
butler provider presets       # butler:// 预设列表
butler provider apply <id> --workspace PATH [--role dev_agent] [--dry-run]
# 微信: /模型 preset minimax-default  或 /模型 save preset …
./scripts/prompt-eval.sh      # CI 守门（含 test_five_reports_p7）
```

SSOT：`mcp-ssot.yaml`、`skills-ssot.yaml`。Prompt eval：`cases.yaml` + `corpus_cases.yaml`。安装前扫描：`BUTLER_INSTALL_PRE_SCAN`（默认开）。Injection 门控：`BUTLER_INJECTION_LLM_SCORE=1` + `BUTLER_INJECTION_LLM_GATE=1`。

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：PR-X3–X6 + M 后续 + P1–P4 深化速查 |
| 2026-05-25 | 五报告 P5：mcp/skills sync、ToolsEngine、reflexion write 等 |
| 2026-05-25 | 五报告 P6：prompt eval、post_session layered、injection LLM、provider presets |
| 2026-05-25 | 五报告 P7：install pre-scan、`mcp scan`、`prompt eval --corpus`、injection human_gate |
| 2026-05-25 | 五报告 P8：`provider apply`、`/模型 preset`、`prompt eval --corpus-live` |
| 2026-05-25 | 五报告 P9：LLM rubric、corpus live smoke、`BUTLER_TOOLS_ENGINE_SSOT` |
| 2026-05-25 | 五报告 P10：thinking beta、`registry verify`、`corpus-live-full`、trading-debate、schema repair×N |
