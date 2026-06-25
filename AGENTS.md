# Cursor / Agent 工作说明（WFXM / Butler v4）

> 新会话先读本文。**不要**用 `docs/history/` 或训练记忆推断实现。

## 必读（按顺序）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | 改 Loop / Gateway / 模块 |
| 2 | [`docs/config/reference.md`](docs/config/reference.md) + [`docs/config/config-surfaces.md`](docs/config/config-surfaces.md) + [`.env.example`](.env.example) | 查 `BUTLER_*`、配置放哪（勿猜默认值） |
| 3 | [`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) | **提需求 / 否决 / Backlog** |
| 4 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层、语料、规划索引、维护规则 |
| 5 | [`docs/plans/decisions/theory-implementation-gap-register-2026-06.md`](docs/plans/decisions/theory-implementation-gap-register-2026-06.md) | 理论—实现差距（G1–G4）；Phase 9 核对见 `post-consolidation-roadmap` §9 |

**发版**：[`docs/guides/release-runbook-2026-05.md`](docs/guides/release-runbook-2026-05.md)

## 代码入口

| 场景 | 路径 |
|------|------|
| Agent 主循环 | `butler/core/agent_loop.py` |
| 微信入站 | `butler/gateway/message_handler.py` |
| 入站队列（实现） | `butler/gateway/message_queue.py` |
| 入站队列（配置） | `butler/gateway/queue_settings.py` |
| 运行指标 | `butler/ops/runtime_metrics.py` |
| Workflow 门控 | `butler/human_gate.py` |
| 向量检索层 | `butler/memory/vector_store.py` |
| Fact 提取 | `butler/core/fact_extraction.py` |
| MCP 自助工具 | `butler/tools/mcp_self_service.py` |
| Skill 工具桥接 | `butler/core/skill_tool_bridge.py` |
| 工具/委派 | `butler/tools/registry.py` |
| 项目级持久待办 | `butler/tools/project_todos.py` |
| 编码知识层 | `butler/dev_engine/coding_knowledge.py` |
| CLI | `butler/main.py` |

## 改代码前守门

```bash
cd /path/to/WFXM
# 本地/PR 快速门禁（smoke quick + 微信附件 + CC 线束，约 3–5 分钟）
./scripts/butler-pytest-fast-gate.sh
# CC 线束（改 core/context/gateway 队列与压缩时）
./scripts/butler-cc-harness-gate.sh
# 或子集：
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/ops/test_runtime_metrics.py \
  tests/test_tool_result_storage.py -q
# gateway / 队列 / workflow
PYTHONPATH=. pytest tests/gateway/test_message_queue.py tests/gateway/test_gateway_queue_command.py \
 tests/test_p2_workflow_permissions.py tests/gateway/test_gateway_handler.py -q
# 或按域：bash scripts/butler-domain-pytest.sh gateway   # ops | dev_engine | memory | core
# 体验增强（总览/待办/管道/引导/自动续跑）
PYTHONPATH=. pytest tests/test_p2_remaining_features.py -q
# 试点项目开发测试（演示试点 / 灵文1号）
bash scripts/butler-pilot-dev-testing.sh
# 编排质量（cron 提醒/向量/语义路由/MCP 自助/fact/Skill 工具联动）
PYTHONPATH=. pytest tests/test_orchestration_improvements.py -q
# 记忆子理论（前提验证 + 度量/基准）
PYTHONPATH=. pytest tests/test_premise_memory_theory.py tests/test_memory_metrics_benchmark.py -q
# 编码知识层（CA1-CA4 / CT1-CT5 / H6/H8/H11）
PYTHONPATH=. pytest tests/test_premise_coding_knowledge.py -q
# 工程桥接（D3-7/8/9 + PIM 注入 + 经验持久化）
PYTHONPATH=. pytest tests/test_engineering_bridge.py -q
# 五报告 P5–P10
./scripts/butler-five-reports-gate.sh
# 配置 env 文档卫生（改 reference.md 时）
bash scripts/check-dead-env.sh
# R8 env_parse（init_dotenv / int_env / float_env）
PYTHONPATH=. pytest tests/test_env_parse_r8.py -q
```

## 勿作实现依据

- `docs/history/`、`reference/`（gitignore）
- `docs/plans/comparisons/*` 正文旧 P0/P2 表（**非待办**）
- `import Hermes AIAgent` / Hermes 子进程网关 — v4 为自建 Loop + 微信 Gateway
- **P0/P2/P3 多义** — 见 [`docs/plans/README.md`](docs/plans/README.md)

## 产品边界（简述）

- **做**：微信管家、多项目、`delegate_task`、runtime、MEMORY、队列 mode、workflow 权限、项目待办、多项目总览
- **不做**：全量 MCP Host、IDE 子进程替代 Loop、入站 WAL、多实例 MQ
- **已做（opt-in）**：workflow 自动续跑（`BUTLER_WORKFLOW_AUTO_RESUME=1`）、terminal 管道（`BUTLER_TERMINAL_PIPE=1`）、首次引导（`BUTLER_ONBOARDING_WELCOME=1`）
- **可选 MCP**：`BUTLER_MCP_ENABLED=1` — [`docs/plans/comparisons/butler-mcp-capability-2026-05.md`](docs/plans/comparisons/butler-mcp-capability-2026-05.md)

## 文档同步义务

改 CC 线束、外部对标模块、四/五报告能力或新增 `BUTLER_*` 时，同步 `v4-architecture`、`config/reference`、`.env.example`、对应 `*-capabilities` 与 [`CONTRIBUTING.md`](CONTRIBUTING.md)。细则见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §6。

索引：[`docs/README.md`](docs/README.md)
