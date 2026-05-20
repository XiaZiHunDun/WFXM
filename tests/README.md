# Butler 测试

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q          # 默认 733 passed，排除 live_llm
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
| `test_butler_*.py`, `test_main_cli.py`, `test_e2e.py` | 产品集成 |
| `test_hermes_extraction.py`, `test_run_agent_extraction.py` | Hermes 提炼回归 |
| `test_real_api_smoke*.py` | 可选真实 API smoke |

v3 时代测试 `test_butler_v3.py` 仍保留用于历史对照；v4 主线以 `test_butler_v4.py` 及 Loop 栈测试为准。
