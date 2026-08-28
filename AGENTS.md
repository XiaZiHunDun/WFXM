# Cursor / Agent 工作说明（WFXM / Butler v5）

> **Butler v5 是唯一活动产品主线；`butler/` v4 已退役。**
> 新会话不要用 v4 文档、`docs/history/` 或训练记忆推断 v5 实现。

> **新会话开篇前 30 秒**：读 `.blackboard/state.md` — 然后再按下面的必读表选读。快照过期时再看最近一张班次卡。交接规约：[`docs/plans/decisions/v5-engineering-handoff-2026-08.md`](docs/plans/decisions/v5-engineering-handoff-2026-08.md)。

## v5 必读（按顺序）

| #   | 文档                                                                                                                 | 何时读                                       |
| --- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| 1   | [`butler-v5/DESIGN.md`](butler-v5/DESIGN.md)                                                                         | 改目标架构、概念、数据、安全或扩展边界       |
| 2   | [`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md) | 查当前生产 Loop、Gateway、工具、数据与调用链 |
| 3   | [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](docs/plans/decisions/v5-product-boundaries-2026-08.md)     | 提需求、否决、条件准入与立项                 |
| 4   | [`docs/architecture/v5-r10-handoff.md`](docs/architecture/v5-r10-handoff.md)                                         | 部署、现状、R-stage 与操作交接               |
| 5   | [`docs/plans/active/v5-post-boundary-roadmap-2026-08.md`](docs/plans/active/v5-post-boundary-roadmap-2026-08.md)     | 后续优先级与安全前置                         |
| 6   | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md)                                                                         | v5 代码约束、包边界和测试                    |
| 7   | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)                                                                     | 文档分层与维护规则                           |

## v5 事实规则

- 生产路径是 `butler-v5/cli + apps/api → packages/runtime → adapters/persistence`。
- 目标架构与当前实现必须分开描述：目标看 `DESIGN.md`，事实看 production architecture。
- `_archive/packages/application` 与部分 `_archive/packages/infrastructure` 当前未接入生产；不得用其单测声称能力已交付。
- 生产数据库 schema 只认 `packages/persistence/src/migrations/0001_initial.sql`。
- 新入口归一化为 Run Trigger；新副作用必须经过 Policy →（Ask 时 waiting_approval）→（需要时 ScopedGrant）→ Provider Boundary → Audit。模型调用不走副作用咽喉。
- MCP、浏览器、UI、多 Channel、调度是**条件准入**，不是默认能力，也不是整类否决。
- **D1 已执行（2026-08-25）**：`~/.butler/` 已删除；回滚见 `~/backup-butler-home-20260825.tgz`。勿删 `~/.config/butler-v5/` 与备份 tgz。

## AI 保护迁移说明

**v5 保护已建立并经 operator 复核（2026-08-27）**：preflight 9/9、post/pre hook 冒烟 PASS（v5 vitest 映射 + 承重文件 block）、`.cursorrules` v5 banner 与 `butler-v5/AGENTS.md` §0 就位，验收见 [`v5-ai-guard-migration-checklist-2026-08.md`](docs/plans/active/v5-ai-guard-migration-checklist-2026-08.md)。

根 `.cursorrules`、hooks 与下方保护表仍包含 v4 保护项，作为 v4 兼容层保留：

- 继续遵守这些保护，不得擅自移除；
- 但它们不是 v5 产品架构或能力现状的事实来源；
- 修改 AI 守卫、`.claude/settings.json` 或受保护文件仍需人工操作（含 `[MANUAL-OVERRIDE]` 提交流程）。

---

## Legacy v4 保护与操作说明（仅守卫兼容，不是产品主线）

## AI 工具保护机制（必读）

本项目已部署多层保护，防止 AI 工具错改代码或造成功能异常。**所有 AI 编码工具（Cursor / Claude Code / Trae / Copilot 等）必须遵守 [`/.cursorrules`](/.cursorrules) 中的规则。**

### 受保护文件（绝不允许 AI 直接修改）

| 类型     | 文件                             | 修改方式           |
| -------- | -------------------------------- | ------------------ |
| 核心循环 | `butler/core/agent_loop/loop.py` | 人工 + 完整门禁    |
| 契约入口 | `butler/contracts/__init__.py`   | 人工 + 契约测试    |
| 项目配置 | `pyproject.toml`                 | 人工 + mypy strict |
| AI 配置  | `.claude/settings.json`          | 人工（防自我解除） |
| AI 守卫  | `scripts/ai_guard/*.py`          | 人工（防自我解除） |
| 交接规约 | `.blackboard/README.md`          | 人工               |

### 保护层

| 层                     | 触发时机                  | 行为                                                                                                                              |
| ---------------------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `.cursorrules`         | AI 工具启动               | 全局行为规则（BLOCK / MUST / SHOULD）                                                                                             |
| `PreToolUse` hook      | Edit/Write/DeleteFile 前  | 阻止修改受保护文件；阻止 `import *` 等危险模式（G4）                                                                              |
| `PostToolUse` hook     | Edit/Write 后             | 自动运行相关测试子集（覆盖 core/gateway/memory/skills/contracts/orchestrator/delegate/workflows/mcp/resilience/hooks/blackboard） |
| `pre-commit` hook      | `git commit` 前           | 层依赖 + 受保护文件 + lazy import 预算（G1）+ secret 扫描（G3）+ 文件大小守卫（G6）                                               |
| 契约测试               | `pytest tests/contracts/` | Port 接口签名稳定（G2）+ Shim `__all__` 一致性（G2）                                                                              |
| `engineering-gates` CI | push / PR                 | G1 lazy import + G2 契约 + G6 文件大小 + G7 env hygiene + ENG-15 层依赖                                                           |
| `Stop` hook            | 会话结束                  | 旧口径仍校验班次卡；目标改为缺卡软提醒，需人工改 settings.json |

### 危险模式（G4，PreToolUse 自动检测）

| 模式                 | 严重程度 | 原因                   |
| -------------------- | -------- | ---------------------- |
| `from X import *`    | BLOCK    | 污染命名空间，隐藏依赖 |
| 注释或删除 `__all__` | WARN     | 破坏模块公共接口契约   |

### 工程约束（G6，pre-commit + CI 自动检查）

| 约束             | 阈值            | 行为                     |
| ---------------- | --------------- | ------------------------ |
| 单文件行数       | >800            | 警告（建议拆分）         |
| 单文件行数       | >1200           | 阻止（必须拆分才能提交） |
| Lazy import 预算 | ≤1910           | 超限阻止提交             |
| Secret 扫描      | API key/JWT/RSA | 检测到即阻止提交         |

### 人工覆盖

受保护文件确需修改时：

1. 在 GitHub 创建 issue 说明原因
2. 由人工执行修改
3. 运行完整门禁：`./scripts/butler-pytest-fast-gate.sh`
4. Git commit 时在 message 中包含 `[MANUAL-OVERRIDE]` 标记

### Shim 文件（约 37 个）

带 `DeprecationWarning` 的 shim 文件是向后兼容层，**不要删除或修改导出列表**。修改功能时只动包目录下的实际实现文件。

## 黑板（班次交接）

工程交接不是产品运行时。默认只维护一份短 `state.md`。完整规约：[`docs/plans/decisions/v5-engineering-handoff-2026-08.md`](docs/plans/decisions/v5-engineering-handoff-2026-08.md)。

**会话开始**：读 `.blackboard/state.md`。快照过期或缺失时再看 `shifts/` 最近一张卡。不要从 `tasks/backlog.yaml`、`log.md` 或缺失的 `MEMORY.md` 推断当前待办。

**会话结束**：把 `state.md` 更新为当前主线、下一步、不要做、上一班一句（约 40 行内）。短会话到此结束。长会话可另写一张短卡。不追加 `log.md`，不改 claims，不强制提交黑板。

`.blackboard/README.md` 与 Claude Code Stop hard gate 仍是受保护旧口径，需人工改到上文。在此之前以本段和交接决策文档为准，不要为过 hook 恢复五件套写卡。

## 代码入口

| 场景                | 路径                                                                                                      |
| ------------------- | --------------------------------------------------------------------------------------------------------- |
| **目录结构总览**    | [`v4-architecture.md`](docs/architecture/v4-architecture.md) §2 九层模型                                  |
| **L1 接入与交互**   | `butler/gateway/`、`butler/cli/`、`butler/main.py`                                                        |
| **L2 编排与控制**   | `butler/orchestrator/`、`butler/workflows/`、`butler/delegate/`                                           |
| **L3 认知推理环**   | `butler/core/`（包：agent_loop/context/compaction/tool/session/llm/loop）                                 |
| **L4 工具与能力**   | `butler/tools/`、`butler/mcp/`、`butler/skills/`、`butler/dev_engine/`                                    |
| **L5 记忆与知识**   | `butler/memory/`                                                                                          |
| **L6 模型与协议**   | `butler/transport/`                                                                                       |
| **L7 策略与门控**   | `butler/permissions/`、`butler/human_gate.py`                                                             |
| **L8 可靠性与韧性** | `butler/resilience/`（message_queue/durable_outbox/idempotency）                                          |
| **L9 观测与运营**   | `butler/ops/`、`butler/eval_integration/`                                                                 |
| **横切**            | `butler/contracts/`、`butler/configuration/`、`butler/utilities/`                                         |
| Agent 主循环        | `butler/core/agent_loop/`（包：loop/phases）                                                              |
| 上下文管线          | `butler/core/context/`（context_pipeline/context_compressor/context_budget）                              |
| 压缩模块            | `butler/core/compaction/`（turn_compaction/turn_summarizer/preemptive_compact）                           |
| 工具模块            | `butler/core/tool/`（tool_batch/tool_dispatch/tool_selector/tool_result_storage）                         |
| 会话模块            | `butler/core/session/`（session_transcript/conversation_state/session_todos）                             |
| LLM 重试            | `butler/core/llm/`（llm_retry/llm_retry_errors/llm_retry_ops）                                            |
| Loop 类型           | `butler/core/loop/`（loop_types/loop_middleware/goal_loop）                                               |
| 配置模块            | `butler/configuration/`（settings/gateway/memory/context/secrets/service/provider_presets）               |
| 工具模块            | `butler/utilities/`（env_parse/logging_config/tenant/repo_paths）                                         |
| 编码知识层          | `butler/dev_engine/coding_knowledge/`（包：elements/theorems/experience/verification/context/generation） |

## 改代码前守门

```bash
cd /path/to/WFXM
# 本地/PR 快速门禁（smoke quick + 微信附件 + CC 线束，约 3–5 分钟）
./scripts/butler-pytest-fast-gate.sh   # smoke + attach + CC harness + mypy strict（约 3–5 分钟）
bash scripts/butler-mypy-strict-gate.sh  # mypy strict 826 主模块（--follow-imports=skip）
bash scripts/p3j-env-hygiene-gate.sh     # reference ↔ .env.example ↔ butler/ readers
bash scripts/p3j-env-audit.sh            # code/reference/example 差集（P3-J）
bash scripts/p3i-lazy-import-report.sh   # 函数内 from butler.* 预算 1901/1910（P3-I）
# 契约测试（Port 接口 + Shim __all__ 一致性，G2）
PYTHONPATH=. pytest tests/contracts/ -q    # 43 测试，<1s
# 文件大小守卫（G6，>800 警告 / >1200 阻止）
python3 scripts/ai_guard/file_size_check.py --ci
# 九层依赖矩阵（改跨层 import / contracts Port / 模块分层迁移时）
bash scripts/butler-layer-import-gate.sh   # ENG-15：1218 文件、0 违规基线
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
# 编排 replay（mock LLM 脚本，无真 API）
PYTHONPATH=. pytest tests/test_llm_response_fixtures.py -q
# 试点项目开发测试（普通试点项目 / 灵文1号）
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

改 CC 线束、外部对标模块、四/五报告能力、**ENG-15 层矩阵/allowlist** 或新增 `BUTLER_*` 时，同步 `v4-architecture`、`v4-layer-model`、`config/reference`、`.env.example`、对应 `*-capabilities` 与 [`CONTRIBUTING.md`](CONTRIBUTING.md)。细则见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §6。

索引：[`docs/README.md`](docs/README.md)
