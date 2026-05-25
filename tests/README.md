# Butler 测试

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q          # 默认全量 ~1816 passed，排除 live_llm（见 pyproject addopts）
butler doctor                   # 静态安全配置审计（OpenClaw OC-P2）
```

## 分层（`pyproject.toml` markers）

| Marker | 含义 |
|--------|------|
| `unit` | L1 单元测试，无 I/O |
| `module_test` | L2 模块测试，mock I/O |
| `integration` | L3 跨模块 |
| `e2e` | L4 端到端 |
| `live_llm` | 真实 API（需 `BUTLER_RUN_REAL_API_SMOKE=1`）|
| `corpus` / `corpus_mock` / `corpus_live` / `corpus_smoke` | 语料模块评测，见 [`corpus/README.md`](corpus/README.md) |

**语料测试（开发对话 + 微信衍射，独立目录）：**

设计：[`docs/plans/corpus-testing-module-design-2026-05.md`](../docs/plans/corpus-testing-module-design-2026-05.md)

```bash
PYTHONPATH=. pytest tests/corpus -m corpus_mock -q
# 或：./scripts/corpus-test.sh mock
```

## 文件分组（按域）

| 前缀 / 文件 | 域 |
|-------------|-----|
| `test_agent_loop.py`, `test_tool_batch.py`, `test_context_pipeline.py` | Agent Loop 栈 |
| `test_transport_*`, `test_llm_client.py`, `test_retry_*` | Transport / LLM |
| `test_gateway_*`, `test_wechat_*`, `test_session_lifecycle.py` | Gateway / 微信 iLink / Session |
| `test_preemptive_compact.py`, `test_post_compact_agents_sections.py`, `test_gateway_openclaw.py`, `test_security_audit.py` | OpenClaw OC-P0–P2 |
| `test_hermes_extraction.py`, `test_run_agent_extraction.py` | Hermes 提炼回归 |
| `test_real_api_smoke*.py`, `test_wechat_gateway_live_smoke.py` | 可选真实 API smoke（`live_llm`） |
| `test_tools_registry.py`, `test_tool_guardrails.py`, `test_path_safety.py` | 工具与安全 |
| `test_orchestrator.py`, `test_task_orchestrator.py`, `test_execution_context.py` | 编排 |
| `test_butler_*.py`, `test_main_cli.py`, `test_cli_scenarios.py`, `test_cli_dimensions.py`, `test_e2e.py` | 产品集成 |
| `cli_harness.py` | CLI 场景测试共用 harness（Rich 捕获、脚本化交互、`ScriptedChatRun`） |
| `butler/cli/slash_commands.py` | 斜杠命令注册、Tab 补全、未知命令校验 |

**微信核心场景 + 项目 Session 隔离（建议改 gateway / session 必跑）：**

```bash
PYTHONPATH=. pytest \
  tests/test_project_manager.py \
  tests/test_project_session_isolation.py \
  tests/test_project_tools_filter.py \
  tests/test_report_format.py \
  tests/test_tenant_isolation.py \
  tests/test_workflows.py \
  tests/test_wechat_session_reset.py \
  tests/test_gateway_acceptance.py \
  tests/test_wechat_ilink_inbound.py \
  tests/test_wechat_ilink_outbound.py \
  tests/test_wechat_ilink_media.py \
  tests/test_owner_profile_gateway.py \
  tests/test_wechat_account_persistence.py \
  tests/test_gateway_runner.py::TestButlerMessageHandlerRunner \
  tests/test_main_cli.py::TestWechatSetupCommand \
  tests/test_session_lifecycle.py \
  tests/test_post_session.py \
  tests/test_p0_memory_pilot.py \
  tests/test_memory_p1_p2.py \
  tests/test_memory_consistency.py \
  tests/test_memory_quality.py \
  tests/test_semantic_memory.py \
  tests/test_memory_reindex.py \
  tests/test_semantic_memory_p1.py \
  tests/test_memory_recall_fixtures.py \
  tests/test_memory_bullet_edit.py \
  tests/test_memory_m3_m4_smoke.py \
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

**Gateway live（微信代码路径 + 真 LLM，发版前可选）**：

```bash
BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... PYTHONPATH=. \
  pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
```

含：单轮问候、README 直读（步骤 3）、委派写文件（步骤 4–4c）、Owner 称呼。

v4 主线以 `test_butler_v4.py`（编排/Loop E2E/CLI）及各 `test_*.py` 模块测试为准；v3/Hermes 嵌入路径已移除。
