# Cursor / Agent 工作说明（WFXM / Butler v5）

> **Butler v5 是唯一活动产品主线；`butler/` v4 已退役。**
> 新会话不要用 v4 文档、`docs/history/` 或训练记忆推断 v5 实现。

> **新会话开篇前 30 秒**：读 `.blackboard/state.md` + `.blackboard/shifts/` 最近一张卡 + `MEMORY.md` — 然后再按下面的必读表选读。

## v5 必读（按顺序）

| # | 文档 | 何时读 |
|---|------|--------|
| 1 | [`docs/architecture/v5-production-architecture-2026-08.md`](docs/architecture/v5-production-architecture-2026-08.md) | 改生产 Loop、Gateway、工具、数据或模块边界 |
| 2 | [`docs/plans/decisions/v5-product-boundaries-2026-08.md`](docs/plans/decisions/v5-product-boundaries-2026-08.md) | 提需求、否决、条件准入与立项 |
| 3 | [`docs/architecture/v5-r10-handoff.md`](docs/architecture/v5-r10-handoff.md) | 部署、现状、R-stage 与操作交接 |
| 4 | [`docs/plans/active/v5-post-boundary-roadmap-2026-08.md`](docs/plans/active/v5-post-boundary-roadmap-2026-08.md) | 后续优先级与安全前置 |
| 5 | [`butler-v5/AGENTS.md`](butler-v5/AGENTS.md) | v5 代码约束、包边界和测试 |
| 6 | [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档分层与维护规则 |

## v5 事实规则

- 生产路径是 `butler-v5/cli + apps/api → packages/runtime → adapters/persistence`。
- `packages/application` 与部分 `packages/infrastructure` 当前未接入生产；不得用其单测声称能力已交付。
- 生产数据库 schema 只认 `packages/persistence/src/migrations/0001_initial.sql`。
- 新入口和新副作用必须遵循 Policy → Approval → Lease → Sandbox → Audit。
- MCP、浏览器、UI、多 Channel、调度是**条件准入**，不是默认能力，也不是整类否决。
- 不要删除 `~/.butler/`，直到 2026-09-18 后 Owner 重新确认 D1。

## AI 保护迁移说明

根 `.cursorrules`、hooks 与下方保护表仍包含 v4 保护项。在等价 v5 保护建立并经人工复核前：

- 继续遵守这些保护，不得擅自移除；
- 但它们不是 v5 产品架构或能力现状的事实来源；
- 修改 AI 守卫、`.claude/settings.json` 或受保护文件仍需人工操作；
- v5 保护迁移按 [`v5-ai-guard-migration-checklist-2026-08.md`](docs/plans/active/v5-ai-guard-migration-checklist-2026-08.md) 由人工执行，不在普通功能变更中顺手修改。

---

## Legacy v4 保护与操作说明（仅守卫兼容，不是产品主线）

## AI 工具保护机制（必读）

本项目已部署多层保护，防止 AI 工具错改代码或造成功能异常。**所有 AI 编码工具（Cursor / Claude Code / Trae / Copilot 等）必须遵守 [`/.cursorrules`](/.cursorrules) 中的规则。**

### 受保护文件（绝不允许 AI 直接修改）

| 类型 | 文件 | 修改方式 |
|------|------|----------|
| 核心循环 | `butler/core/agent_loop/loop.py` | 人工 + 完整门禁 |
| 契约入口 | `butler/contracts/__init__.py` | 人工 + 契约测试 |
| 项目配置 | `pyproject.toml` | 人工 + mypy strict |
| AI 配置 | `.claude/settings.json` | 人工（防自我解除） |
| AI 守卫 | `scripts/ai_guard/*.py` | 人工（防自我解除） |
| 交接规约 | `.blackboard/README.md` | 人工 |

### 保护层

| 层 | 触发时机 | 行为 |
|----|----------|------|
| `.cursorrules` | AI 工具启动 | 全局行为规则（BLOCK / MUST / SHOULD） |
| `PreToolUse` hook | Edit/Write/DeleteFile 前 | 阻止修改受保护文件；阻止 `import *` 等危险模式（G4） |
| `PostToolUse` hook | Edit/Write 后 | 自动运行相关测试子集（覆盖 core/gateway/memory/skills/contracts/orchestrator/delegate/workflows/mcp/resilience/hooks/blackboard） |
| `pre-commit` hook | `git commit` 前 | 层依赖 + 受保护文件 + lazy import 预算（G1）+ secret 扫描（G3）+ 文件大小守卫（G6） |
| 契约测试 | `pytest tests/contracts/` | Port 接口签名稳定（G2）+ Shim `__all__` 一致性（G2） |
| `engineering-gates` CI | push / PR | G1 lazy import + G2 契约 + G6 文件大小 + G7 env hygiene + ENG-15 层依赖 |
| `Stop` hook | 会话结束 | 黑板交接卡校验（hard gate） |

### 危险模式（G4，PreToolUse 自动检测）

| 模式 | 严重程度 | 原因 |
|------|----------|------|
| `from X import *` | BLOCK | 污染命名空间，隐藏依赖 |
| 注释或删除 `__all__` | WARN | 破坏模块公共接口契约 |

### 工程约束（G6，pre-commit + CI 自动检查）

| 约束 | 阈值 | 行为 |
|------|------|------|
| 单文件行数 | >800 | 警告（建议拆分） |
| 单文件行数 | >1200 | 阻止（必须拆分才能提交） |
| Lazy import 预算 | ≤1910 | 超限阻止提交 |
| Secret 扫描 | API key/JWT/RSA | 检测到即阻止提交 |

### 人工覆盖

受保护文件确需修改时：
1. 在 GitHub 创建 issue 说明原因
2. 由人工执行修改
3. 运行完整门禁：`./scripts/butler-pytest-fast-gate.sh`
4. Git commit 时在 message 中包含 `[MANUAL-OVERRIDE]` 标记

### Shim 文件（约 37 个）

带 `DeprecationWarning` 的 shim 文件是向后兼容层，**不要删除或修改导出列表**。修改功能时只动包目录下的实际实现文件。

## 黑板（班次交接）

**会话开始**：

```bash
# 1. 看快照
cat .blackboard/state.md
# 2. 看上一班次（最近 1-2 张）
ls -t .blackboard/shifts/ | head -2
# 3. 看交接包（若想一屏看完）
butler blackboard handoff --root .
```

**会话结束**（hard gate）：

```bash
# 写卡：手动按 .blackboard/README.md 规约；或跑
butler blackboard validate --shift-id <shift_id>   # 校验
# append log.md 一段
# 更新 claim（如有）+ backlog.yaml（如有状态变化）
# commit 这一组变更
```

**Hook 提醒**：项目根 `.claude/settings.json` 已配 Stop hook，跑
`BLACKBOARD_STRICT=1 BLACKBOARD_AGENT=claude-code python3 -m butler.blackboard.integrations.claude_session_end`：
- 缺卡 → stderr 提醒 + exit 2（**hard gate**，阻断退出）。
- 有卡 → 自动找今日最新卡并跑 `butler blackboard validate`；通过 exit 0，
  失败 exit 2。
- 关掉 hard gate：删 `.claude/settings.json` 的 `hooks.Stop`，或去掉命令前的
  `BLACKBOARD_STRICT=1`（退回软提醒模式）。

## 代码入口

| 场景 | 路径 |
|------|------|
| **目录结构总览** | [`v4-architecture.md`](docs/architecture/v4-architecture.md) §2 九层模型 |
| **L1 接入与交互** | `butler/gateway/`、`butler/cli/`、`butler/main.py` |
| **L2 编排与控制** | `butler/orchestrator/`、`butler/workflows/`、`butler/delegate/` |
| **L3 认知推理环** | `butler/core/`（包：agent_loop/context/compaction/tool/session/llm/loop） |
| **L4 工具与能力** | `butler/tools/`、`butler/mcp/`、`butler/skills/`、`butler/dev_engine/` |
| **L5 记忆与知识** | `butler/memory/` |
| **L6 模型与协议** | `butler/transport/` |
| **L7 策略与门控** | `butler/permissions/`、`butler/human_gate.py` |
| **L8 可靠性与韧性** | `butler/resilience/`（message_queue/durable_outbox/idempotency） |
| **L9 观测与运营** | `butler/ops/`、`butler/eval_integration/` |
| **横切** | `butler/contracts/`、`butler/configuration/`、`butler/utilities/` |
| Agent 主循环 | `butler/core/agent_loop/`（包：loop/phases） |
| 上下文管线 | `butler/core/context/`（context_pipeline/context_compressor/context_budget） |
| 压缩模块 | `butler/core/compaction/`（turn_compaction/turn_summarizer/preemptive_compact） |
| 工具模块 | `butler/core/tool/`（tool_batch/tool_dispatch/tool_selector/tool_result_storage） |
| 会话模块 | `butler/core/session/`（session_transcript/conversation_state/session_todos） |
| LLM 重试 | `butler/core/llm/`（llm_retry/llm_retry_errors/llm_retry_ops） |
| Loop 类型 | `butler/core/loop/`（loop_types/loop_middleware/goal_loop） |
| 配置模块 | `butler/configuration/`（settings/gateway/memory/context/secrets/service/provider_presets） |
| 工具模块 | `butler/utilities/`（env_parse/logging_config/tenant/repo_paths） |
| 编码知识层 | `butler/dev_engine/coding_knowledge/`（包：elements/theorems/experience/verification/context/generation） |

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
