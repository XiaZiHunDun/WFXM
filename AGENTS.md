# Cursor / Agent 工作说明（WFXM / Butler v4）

> 新会话请先读本文，再按需打开链接。**不要**用训练记忆或 `docs/history/` 推断当前实现。

## 单一事实来源（按优先级）

| 优先级 | 文档 | 用途 |
|--------|------|------|
| 1 | [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | **当前**模块划分、Loop/Gateway 数据流、P0–P2 线束 |
| 2 | [`docs/config/reference.md`](docs/config/reference.md) + [`.env.example`](.env.example) | `BUTLER_*` 环境变量（勿猜默认值） |
| 3 | [`docs/plans/cc-butler-gap-analysis-2026-05.md`](docs/plans/cc-butler-gap-analysis-2026-05.md) | Claude Code 对照；**CC 线束 P0–P4**（§4–§11，勿与 consolidation-P3 混淆） |
| 4 | [`STRUCTURE.md`](STRUCTURE.md) | 目录树与常用命令 |
| 5 | [`CONTRIBUTING.md`](CONTRIBUTING.md) | 微信线束、Hooks、出站推送、发版抽测 H1–H11 |
| 6 | [`docs/design/design.md`](docs/design/design.md) | 产品设计摘要；§9 为对照表，**§11+ 可能过时** |

索引：[`docs/README.md`](docs/README.md)

## 已过时或易误导（勿作为实现依据）

- `docs/history/*` — v0.5–v3、`AgentRunner`、`butler/agent/` 等**已删除或归档**
- `reference/` — 外部对照区，**gitignore**，与 Butler 产品代码无关
- **P2 / P3 / P4 多义**：**CC 线束**见 `cc-butler-gap-analysis`（P2=流式预取等，P3/P4=§11 深挖）；**仓库整理 P3**见 `consolidation-p3-implementation-2026-05.md`（死代码清理，已完成）
- **不要**声称 `import Hermes AIAgent` 或 Hermes 子进程网关 — v4 为自建 Loop + 原生微信 Gateway

## 代码入口

| 场景 | 路径 |
|------|------|
| Agent 主循环 | `butler/core/agent_loop.py` |
| 微信入站 | `butler/gateway/message_handler.py` |
| 工具/委派 | `butler/tools/registry.py` |
| 编排/模型/记忆 | `butler/orchestrator.py` |
| CLI / 网关启动 | `butler/main.py` |

## 改代码前建议执行的核对

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_runtime_metrics.py tests/test_tool_result_storage.py -q
# 改 gateway：再加 tests/test_message_queue.py tests/test_gateway_handler.py（部分用例可能与 reason=clear 等历史 mock 不一致）
```

## 产品边界（简述）

- **做**：微信管家、多项目、`delegate_task`、runtime jobs、项目 `MEMORY.md`
- **不做**：内置 MCP host、控制 IDE、Claude Code 子进程替代 Loop

## 文档更新义务

若改动 CC 线束（P0–P4）或新增 `BUTLER_*` 变量，请同步：`docs/architecture/v4-architecture.md`、`docs/config/reference.md`、`.env.example`、`CONTRIBUTING.md`（Butler 线束节）。
