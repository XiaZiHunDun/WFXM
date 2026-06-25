# Butler 测试

> **Agent / LLM 时代测试原则**：[`docs/plans/decisions/agent-testing-strategy-2026-06.md`](../docs/plans/decisions/agent-testing-strategy-2026-06.md)（四层模型 · 断言契约 · CI 矩阵）

```bash
cd /path/to/WFXM
PYTHONPATH=. pytest -q          # 默认 ~6565 selected / 7110 collected（排除 live_llm 545）
bash scripts/project-health-check.sh quick   # 统一体检（代码+配置+关键测试）
bash scripts/project-health-check.sh full    # 加跑 corpus + 五报告守门
bash scripts/project-health-report.sh quick  # 体检并落盘报告
bash scripts/repo-cleanup-audit.sh           # 结构漂移/大文件审计
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

## Agent 测试四层（速查）

| 层 | 测什么 | 默认 CI | 入口 |
|----|--------|---------|------|
| **L-A 确定性** | Gateway、工具、格式化、附件 | ✅ | `butler-pytest-fast-gate.sh`、domain pytest |
| **L-B 编排** | Loop + mock LLM 脚本 | ✅ | `tests/test_llm_response_fixtures.py`、`tests/fixtures/llm_responses/` |
| **L-C 行为** | handler sim、文件/task 契约 | opt-in | `butler-pilot-dev-testing.sh`、`butler-wechat-*-sim.sh` |
| **L-D 质量** | live_llm、语料 live、LangFuse | nightly/月 | `-m live_llm`、`butler-dev-flywheel-monthly.sh` |

**编排 replay 示例**：

```bash
PYTHONPATH=. pytest tests/test_llm_response_fixtures.py -q
```

**语料测试（开发对话 + 微信衍射，独立目录）：**

设计：[`docs/plans/corpus/corpus-testing-module-design-2026-05.md`](../docs/plans/corpus/corpus-testing-module-design-2026-05.md)

```bash
PYTHONPATH=. pytest tests/corpus -m corpus_mock -q
# 或：./scripts/corpus-test.sh mock
```

## 目录域（2026-06-23 起）

新测优先放入子目录；`test_sprint*` 等历史文件暂留 `tests/` 根目录（自动打 `legacy_sprint` marker，见 `pyproject.toml`）。

| 目录 | 职责 | 守门命令 |
|------|------|----------|
| [`gateway/`](gateway/README.md) | 微信网关、斜杠命令、入站队列 | `bash scripts/butler-domain-pytest.sh gateway` |
| [`ops/`](ops/README.md) | eval、metrics、health report、G1 证据 | `bash scripts/butler-domain-pytest.sh ops` |
| [`dev_engine/`](dev_engine/README.md) | VERIFY、read_state、dev 集成 | `bash scripts/butler-domain-pytest.sh dev_engine` |
| [`memory/`](memory/) | 记忆子系统、R5 并发 | 见目录内测试 |
| [`core/`](core/) | Loop / context 并发 | 见目录内测试 |
| [`corpus/`](corpus/README.md) | 语料评测（独立体系） | `./scripts/corpus-test.sh mock` |
| `tests/` 根 | 历史 sprint（`legacy_sprint`）/ 跨域集成 | 全量 `pytest -q` |

**`legacy_sprint` 迁移策略**：新功能测写入 `tests/<domain>/`；根目录 `test_sprint*` 仅做回归保留，不新增。可选跳过：`pytest -m 'not legacy_sprint'`。

```bash
bash scripts/butler-domain-pytest.sh gateway ops dev_engine   # 多域
bash scripts/butler-domain-pytest.sh all                      # 等同全量 pytest
```

## 文件分组（按域 · 根目录遗留）

> 下列前缀文件已迁入上表子目录；根目录仅保留 sprint 与跨域集成。

| 前缀 / 文件 | 域 |
|-------------|-----|
| `tests/gateway/test_gateway_*`, `test_wechat_*` | Gateway（已迁入） |
| `tests/ops/test_eval_*`, `test_runtime_metrics.py` | Ops（已迁入） |
| `tests/dev_engine/test_verify_*` | DevEngine（已迁入） |
| `test_agent_loop.py`, `test_tool_batch.py`, `test_context_pipeline.py` | Agent Loop 栈 |
| `test_transport_*`, `test_llm_client.py`, `test_retry_*` | Transport / LLM |
| `test_gateway_*`, `test_wechat_*`, `test_session_lifecycle.py` | Gateway / 微信 iLink / Session（→ `tests/gateway/`） |
| `test_preemptive_compact.py`, `test_post_compact_agents_sections.py`, `test_gateway_openclaw.py`, `test_security_audit.py` | OpenClaw OC-P0–P2 |
| `test_sprint_codex_c0.py`, `test_sprint_codex_c1.py`, `test_sprint_codex_c2.py` | Codex 对标 Sprint C0–C2 |
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
  tests/gateway/test_wechat_session_reset.py \
  tests/gateway/test_gateway_acceptance.py \
  tests/gateway/test_wechat_ilink_inbound.py \
  tests/gateway/test_wechat_ilink_outbound.py \
  tests/gateway/test_wechat_ilink_media.py \
  tests/gateway/test_owner_profile_gateway.py \
  tests/gateway/test_wechat_account_persistence.py \
  tests/gateway/test_gateway_runner.py::TestButlerMessageHandlerRunner \
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
  pytest -m live_llm tests/gateway/test_wechat_gateway_live_smoke.py -v
```

含：单轮问候、README 直读（步骤 3）、委派写文件（步骤 4–4c）、Owner 称呼。

v4 主线以 `test_butler_v4.py`（编排/Loop E2E/CLI）及各 `test_*.py` 模块测试为准；v3/Hermes 嵌入路径已移除。
