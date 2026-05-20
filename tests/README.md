# Butler 测试

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q          # 默认 ~925 passed，排除 live_llm 与 tests/archive/
```

## 分层（`pyproject.toml` markers）

| Marker | 含义 |
|--------|------|
| `unit` | L1 单元测试，无 I/O |
| `module_test` | L2 模块测试，mock I/O |
| `integration` | L3 跨模块 |
| `e2e` | L4 端到端 |
| `live_llm` | 真实 API（需 `BUTLER_RUN_REAL_API_SMOKE=1`）|

## 文件分组（按域）

| 前缀 / 文件 | 域 |
|-------------|-----|
| `test_agent_loop.py`, `test_tool_batch.py`, `test_context_pipeline.py` | Agent Loop 栈 |
| `test_transport_*`, `test_llm_client.py`, `test_retry_*` | Transport / LLM |
| `test_gateway_*`, `test_session_lifecycle.py` | Gateway / Session |
| `test_tools_registry.py`, `test_tool_guardrails.py`, `test_path_safety.py` | 工具与安全 |
| `test_orchestrator.py`, `test_task_orchestrator.py`, `test_execution_context.py` | 编排 |
| `test_butler_*.py`, `test_main_cli.py`, `test_cli_scenarios.py`, `test_cli_dimensions.py`, `test_e2e.py` | 产品集成 |
| `cli_harness.py` | CLI 场景测试共用 harness（Rich 捕获、脚本化交互、`ScriptedChatRun`） |
| `butler/cli/slash_commands.py` | 斜杠命令注册、Tab 补全、未知命令校验 |

**微信核心场景 + 项目 Session 隔离（建议改 gateway / session 必跑）：**

```bash
PYTHONPATH=. pytest \
  tests/test_project_session_isolation.py \
  tests/test_project_tools_filter.py \
  tests/test_report_format.py \
  tests/test_tenant_isolation.py \
  tests/test_workflows.py \
  tests/test_wechat_session_reset.py \
  tests/test_gateway_acceptance.py \
  tests/test_wechat_ilink_inbound.py \
  tests/test_session_lifecycle.py \
  tests/test_post_session.py \
  -q
```

**CLI 专项（建议改 CLI 必跑）：**

```bash
PYTHONPATH=. pytest tests/test_cli_scenarios.py tests/test_cli_dimensions.py -q
```

**CLI + 真实 MiniMax（本地有 Key 时）：**

```bash
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_cli_live_smoke.py -v
```
| `test_hermes_extraction.py`, `test_run_agent_extraction.py` | Hermes 提炼回归 |
| `test_real_api_smoke*.py` | 可选真实 API smoke |

v3 遗留测试见 `tests/archive/test_butler_v3.py`（默认不收集）；v4 主线以 `test_butler_v4.py` 及 Loop 栈测试为准。
