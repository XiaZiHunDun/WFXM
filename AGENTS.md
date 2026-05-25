# Cursor / Agent 工作说明（WFXM / Butler v4）

> 新会话请先读本文，再按需打开链接。**不要**用训练记忆或 `docs/history/` 推断当前实现。

## 单一事实来源（按优先级）

| 优先级 | 文档 | 用途 |
|--------|------|------|
| 1 | [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | **当前**模块划分、Loop/Gateway、CC 线束 + 外部对标落地 |
| 2 | [`docs/config/reference.md`](docs/config/reference.md) + [`.env.example`](.env.example) | `BUTLER_*` 环境变量（勿猜默认值） |
| 3 | [`docs/plans/cc-butler-gap-analysis-2026-05.md`](docs/plans/cc-butler-gap-analysis-2026-05.md) | Claude Code 对照；**CC 线束 P0–P4**（§4–§11） |
| 4 | [`docs/plans/README.md`](docs/plans/README.md) | 规划索引；**三套 P0/P2/P3 命名对照** |
| 4b | [`docs/plans/four-reports-out-of-scope-2026-05.md`](docs/plans/four-reports-out-of-scope-2026-05.md) | 四报告对标 **明确不做**（新增能力前先查） |
| 4c | [`docs/plans/five-reports-improvement-roadmap-2026-05.md`](docs/plans/five-reports-improvement-roadmap-2026-05.md) | 五报告合并路线图（**已落地**，主线 F–J / PR-F1–F6）；速查 [`docs/guides/five-reports-capabilities-2026-05.md`](docs/guides/five-reports-capabilities-2026-05.md) |
| 4d | [`docs/plans/five-reports-not-done-2026-05.md`](docs/plans/five-reports-not-done-2026-05.md) | 五报告**未作**（S1–S11 否决 + P2 未排期）；与四报告 out-of-scope 并用 |
| 5 | [`STRUCTURE.md`](STRUCTURE.md) | 目录树与常用命令 |
| 6 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | 微信线束、Hooks、出站、队列/workflow、发版抽测 |
| 7 | [`docs/design/design.md`](docs/design/design.md) | 产品设计摘要；§9 为对照表，**§11+ 可能过时** |

索引：[`docs/README.md`](docs/README.md)

## 已过时或易误导（勿作为实现依据）

- `docs/history/*` — v0.5–v3、`AgentRunner`、`butler/agent/` 等**已删除或归档**
- `reference/` — 外部对照区，**gitignore**，与 Butler 产品代码无关
- **P0/P2/P3 多义**（见 [`docs/plans/README.md`](docs/plans/README.md)）：
  - **CC 线束** P0–P4 → `cc-butler-gap-analysis`
  - **仓库整理** P3 → `consolidation-p3-implementation`（死代码清理，已完成）
  - **外部对标** P0–P2 → `reference-learning-plan`（**已收口**，零依赖）
  - **OpenCode 对标** P0–P1 → `opencode-learning-plan`（压缩/prune/权限/doom loop/委派）
- **不要**声称 `import Hermes AIAgent` 或 Hermes 子进程网关 — v4 为自建 Loop + 原生微信 Gateway

## 代码入口

| 场景 | 路径 |
|------|------|
| Agent 主循环 | `butler/core/agent_loop.py` |
| 微信入站 | `butler/gateway/message_handler.py` |
| 入站队列策略 | `butler/gateway/queue_settings.py` |
| 运行指标 | `butler/ops/runtime_metrics.py` |
| Workflow 人工门控 | `butler/human_gate.py` |
| 工具/委派 | `butler/tools/registry.py` |
| 编排/模型/记忆 | `butler/orchestrator.py` |
| CLI / 网关启动 | `butler/main.py` |

## 改代码前建议执行的核对

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_runtime_metrics.py \
  tests/test_tool_result_storage.py -q

# 改 gateway / 队列 / workflow
PYTHONPATH=. pytest tests/test_message_queue.py tests/test_gateway_queue_command.py \
  tests/test_p2_workflow_permissions.py tests/test_gateway_handler.py -q

# 改四报告增量（RAG / DESIGN / 实验 / Loop 减熵）
PYTHONPATH=. pytest tests/test_ragflow_p0_retrieval.py tests/test_design_md_sections.py \
  tests/test_experiment_ledger.py tests/test_query_decompose.py tests/test_support_line_e.py -q
```

## 产品边界（简述）

- **做**：微信管家、多项目、`delegate_task`、runtime jobs、项目 `MEMORY.md`、入站队列 mode、`workflow_steps` 权限
- **不做**：OpenCode/CC 级 MCP Host（npm 生态、OAuth 浏览器）；控制 IDE、Claude 子进程替代 Loop；入站 jsonl WAL、自动续跑 workflow、多实例 MQ
- **可选 MCP**：`BUTLER_MCP_ENABLED=1` + `pip install butler-system[mcp]` + `.butler/mcp.yaml`；见 [`docs/plans/butler-mcp-capability-2026-05.md`](docs/plans/butler-mcp-capability-2026-05.md)

## 文档更新义务

若改动 **CC 线束**、**外部对标模块**（`runtime_metrics` / `queue_settings` / `human_gate`）、**四报告增量**（`butler/memory/chunking`、`design_md_sections`、`butler/experiments/`、`query_decompose` 等）或新增 `BUTLER_*`，请同步：

- `docs/architecture/v4-architecture.md`
- `docs/config/reference.md`、`.env.example`
- `CONTRIBUTING.md`（Butler 线束节）
- 四报告能力变更时：`docs/guides/four-reports-capabilities-2026-05.md`、`docs/plans/four-reports-improvement-roadmap-2026-05.md` §9
- 阈值变更时：`docs/ops/diagnostic-thresholds.md`
