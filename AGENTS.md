# Cursor / Agent 工作说明（WFXM / Butler v4）

> 新会话先读本文。**不要**用 `docs/history/` 或训练记忆推断实现。

## 必读（按顺序）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | 改 Loop / Gateway / 模块 |
| 2 | [`docs/config/reference.md`](docs/config/reference.md) + [`.env.example`](.env.example) | 查 `BUTLER_*`（勿猜默认值） |
| 3 | [`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) | **提需求 / 否决 / Backlog** |
| 4 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层、语料、规划索引、维护规则 |

**发版**：[`docs/guides/release-runbook-2026-05.md`](docs/guides/release-runbook-2026-05.md)

## 代码入口

| 场景 | 路径 |
|------|------|
| Agent 主循环 | `butler/core/agent_loop.py` |
| 微信入站 | `butler/gateway/message_handler.py` |
| 入站队列 | `butler/gateway/queue_settings.py` |
| 运行指标 | `butler/ops/runtime_metrics.py` |
| Workflow 门控 | `butler/human_gate.py` |
| 工具/委派 | `butler/tools/registry.py` |
| CLI | `butler/main.py` |

## 改代码前守门

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_runtime_metrics.py \
  tests/test_tool_result_storage.py -q
# gateway / 队列 / workflow
PYTHONPATH=. pytest tests/test_message_queue.py tests/test_gateway_queue_command.py \
  tests/test_p2_workflow_permissions.py tests/test_gateway_handler.py -q
# 五报告 P5–P10
./scripts/butler-five-reports-gate.sh
```

## 勿作实现依据

- `docs/history/`、`reference/`（gitignore）
- `docs/plans/comparisons/*` 正文旧 P0/P2 表（**非待办**）
- `import Hermes AIAgent` / Hermes 子进程网关 — v4 为自建 Loop + 微信 Gateway
- **P0/P2/P3 多义** — 见 [`docs/plans/README.md`](docs/plans/README.md)

## 产品边界（简述）

- **做**：微信管家、多项目、`delegate_task`、runtime、MEMORY、队列 mode、workflow 权限
- **不做**：全量 MCP Host、IDE 子进程替代 Loop、入站 WAL、workflow 自动续跑、多实例 MQ
- **可选 MCP**：`BUTLER_MCP_ENABLED=1` — [`docs/plans/comparisons/butler-mcp-capability-2026-05.md`](docs/plans/comparisons/butler-mcp-capability-2026-05.md)

## 文档同步义务

改 CC 线束、外部对标模块、四/五报告能力或新增 `BUTLER_*` 时，同步 `v4-architecture`、`config/reference`、`.env.example`、对应 `*-capabilities` 与 [`CONTRIBUTING.md`](CONTRIBUTING.md)。细则见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §6。

索引：[`docs/README.md`](docs/README.md)
