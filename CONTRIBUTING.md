# 贡献指南

## 微信 Gateway 语料与路由

修改以下路径时，请在提交前跑通 **语料 PR 门禁**（与 CI `corpus-pr-gate` job 一致）：

- `butler/gateway/message_handler.py` 及 `butler/gateway/`
- `tests/corpus/`
- `tests/test_gateway_dev_conversations.py`

```bash
./scripts/corpus-test.sh drift    # 生成物与脚本一致
./scripts/corpus-test.sh pr-gate  # 有 diff 时跑 unified mock（AgentLoop + 微信语料 + 交叉索引）
```

也可强制全量：

```bash
CORPUS_PR_GATE_FORCE=1 ./scripts/corpus-test.sh pr-gate
```

本地对照 PR 基线：

```bash
CORPUS_PR_GATE_BASE=origin/main ./scripts/corpus-test.sh pr-gate
```

## 常用语料命令

| 命令 | 说明 |
|------|------|
| `./scripts/corpus-test.sh gateway` | L0–L2 微信 mock 一键 |
| `./scripts/corpus-test.sh unified` | 全量 mock + cross_channel |
| `./scripts/corpus-test.sh gateway-live` | L3 live（需 `.env` 与 `MINIMAX_API_KEY`） |
| `./scripts/corpus-test.sh drift` | YAML 漂移检查 |

设计说明见 [`docs/plans/corpus/corpus-testing-module-design-2026-05.md`](docs/plans/corpus/corpus-testing-module-design-2026-05.md) 与 `tests/corpus/suites/wechat_real/lw_real/meta.yaml`。语料文档索引见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) §5。

## 发版

发版顺序见 [`docs/guides/release-runbook-2026-05.md`](docs/guides/release-runbook-2026-05.md)（preflight → `butler-pre-release-smoke.sh` → 网关部署 → 真机清单）。

## Butler 线束（规划 / 上下文 / Hooks）

- 微信：`/计划`、`/执行`、`/任务`；`/诊断` 含上下文用量档位、Shell hooks 摘要、**出站策略**（完成推送/委派模式/冷却）；`/状态` 含规划模式
- 可选环境变量：`BUTLER_DISABLE_AUTO_COMPACT`、`BUTLER_CONTEXT_*`、`BUTLER_MEMORY_MAX_LINES`
- 大工具结果落盘：`BUTLER_TOOL_RESULT_SPILL`（默认开）→ `~/.butler/sessions/<session>/tool-results/`；上下文为 `<persisted-output>` 指针，需完整内容时用 `read_file`
- 工具分级剪枝：`BUTLER_TOOL_PRUNE_*`；压缩后 `post_compact` 重注入 MEMORY/任务锚点；`/诊断` 含 **上轮循环结束**（`loop_transition_reason`）
- 读后再改：`BUTLER_READ_BEFORE_EDIT=1` 时 `patch`/`write_file`（覆盖已有文件）须先 `read_file`，且校验 mtime；`/新对话` 清空 read state
- P1：长轮次中重复入站进队列（`BUTLER_GATEWAY_MESSAGE_QUEUE`）；Stop 钩子可 `exit 2` 或 JSON `decision:block`；句末 `+500k` / `/budget` / 「本轮尽量做完」提高 `max_iterations`
- P2：流式只读工具预取（`BUTLER_STREAMING_TOOLS`）；`delegate_task` cache-safe 前缀（`BUTLER_CACHE_SAFE_DELEGATE`）；队列 drain 单独推送（`BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE`）
- **外部对标（已收口，零依赖）**：`runtime_metrics` → `/诊断` 运行指标（[`docs/ops/diagnostic-thresholds.md`](docs/ops/diagnostic-thresholds.md)）；入站 `BUTLER_GATEWAY_QUEUE_MODE`（followup/collect/interrupt/steer）与会话 `/queue`；workflow `requires_approval` → `/确认` `/取消` 后再发 `/workflow`（见 [`docs/plans/archive/reference-learning-plan-2026-05.md`](docs/plans/archive/reference-learning-plan-2026-05.md)）
- **OpenCode 对标（P0–P1）**：压缩模板、`BUTLER_TOOL_PRUNE_BACKWARD*`、`BUTLER_DOOM_LOOP_THRESHOLD`、权限 last-match、`instruction_walkup`、`delegate_subagent`（见 [`docs/plans/comparisons/opencode-learning-plan-2026-05.md`](docs/plans/comparisons/opencode-learning-plan-2026-05.md)）
- **MCP 薄客户端（P3，默认关）**：`pip install butler-system[mcp]` + `BUTLER_MCP_ENABLED=1` + `~/.butler/mcp.yaml`；`project.yaml` 须含 `mcp_*`；`/诊断` 含 MCP 连接段；开发：`butler mcp serve`（见 [`docs/plans/comparisons/butler-mcp-capability-2026-05.md`](docs/plans/comparisons/butler-mcp-capability-2026-05.md)）
- **OpenClaw 对标（OC-P0–P2，默认多数开）**：`preemptive_compact`（LLM 前压缩路由）；AGENTS.md 节 post-compact 回灌；`tool_loop_detect`（ping_pong/poll/circuit）；`reply_admission` 单飞；`bot_loop_guard`（默认关）；`butler doctor` / 微信 `/doctor`；Owner `/批准执行` + `delegate_yield`（见 [`docs/plans/comparisons/openclaw-learning-plan-2026-05.md`](docs/plans/comparisons/openclaw-learning-plan-2026-05.md)）
- **依赖分层原则**：默认 `pip install -e .` 只覆盖 core 主路径；微信/MCP/voice/OCR/PTY 依赖走 `optional-dependencies`；不要把 Effect、Redis、Postgres、全量 MCP Host、桌面壳依赖拉进 core
- **DESIGN.md（UI 项目，PR5）**：根目录或 `.butler/design/DESIGN.md`；可选 `project.yaml` 的 `design_preset`；`butler/core/design_md_sections.py` 负责压缩后回灌与 orchestrator 摘要；委派 `category=ui-build`；内置工作流 `ui-dev-qa-loop`；技能模板 [`docs/templates/skills/design-system.md`](docs/templates/skills/design-system.md)
- **实验组织（PR6）**：模板 `software-research`；`.butler/harness/` 只读 + `experiments/` 可写（`BUTLER_EXPERIMENT_MODE=1`）；账本 `.butler/experiments.tsv`；harness stdout 打印 `METRIC name=value`；CLI `butler experiment list|record|best|discard`；见 [`docs/templates/experiments/README.md`](docs/templates/experiments/README.md)
- **检索子 query**：`BUTLER_RAG_SUBQUERY=1` 时复合问句拆为多路检索合并；`/诊断` 显示子 query 数
- **内置技能种子**：首次加载租户 ButlerMemory 时安装 `tenants/<id>/skills/design-system.md`（源 [`docs/templates/skills/design-system.md`](docs/templates/skills/design-system.md)）
- **支撑线 E（P2 子集）**：workflow 步骤与 `project.yaml` 工具列表求交；`tool_modes` 按角色缩工具；`BUTLER_TOOL_IMPLICIT_CONTEXT`；`BUTLER_SCHEMA_OPTIMIZE`；`BUTLER_TOKEN_COST_ESTIMATE`
- **研究模式补充**：`PROGRAM.md` + skill `research-program`；连续 crash 阻断提示；post-compact 简洁性锚点 — 见 [`docs/plans/roadmaps/four-reports-improvement-roadmap-2026-05.md`](docs/plans/roadmaps/four-reports-improvement-roadmap-2026-05.md) §9
- **五报告增量（PR-F1–F6）**：outcome log（`/评价`）、handoff、熔断/sessions、`butler_recall` 三层、工具错误策略、Pipeline 步骤诊断 — 见 [`docs/guides/five-reports-capabilities-2026-05.md`](docs/guides/five-reports-capabilities-2026-05.md)
- **否决 / 未做 / Backlog**：见 [`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)（**提需求先读**）；五报告 S1–S11 速查 [`five-reports-not-done`](docs/plans/decisions/five-reports-not-done-2026-05.md)；四报告 18 项 [`four-reports-out-of-scope`](docs/plans/decisions/four-reports-out-of-scope-2026-05.md)
- **文档维护**：见 [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md)
- **发版后真机抽测（约 10 分钟）**：[`docs/guides/wechat-daily-smoke-checklist.md`](docs/guides/wechat-daily-smoke-checklist.md#线束与长任务完成提醒发版后建议-10-分钟) 表 **H1–H10**（规划、Hooks、委派完成推送、progress ack、入队 drain）

```bash
# 文档/队列/workflow 相关守门
PYTHONPATH=. pytest tests/test_runtime_metrics.py tests/test_message_queue.py \
  tests/test_gateway_queue_command.py tests/test_p2_workflow_permissions.py \
  tests/test_opencode_features.py tests/test_opencode_p2_features.py \
  tests/test_mcp_features.py -q

# 四报告增量（RAG / DESIGN / 实验 / Loop 减熵）
PYTHONPATH=. pytest tests/test_ragflow_p0_retrieval.py tests/test_design_md_sections.py \
  tests/test_experiment_ledger.py tests/test_query_decompose.py tests/test_support_line_e.py \
  tests/test_roadmap_remainder.py tests/test_markdown_chunking.py tests/test_loop_pr2_entropy.py -q

# 五报告 P5–P10（SSOT / eval / registry / harness）— 一条命令
./scripts/butler-five-reports-gate.sh
# 可选 live：BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=… butler prompt eval --corpus-live-smoke

# 五报告 PR-F1–F6（主线 F–J 基线）
PYTHONPATH=. pytest tests/test_lobehub_p0_features.py tests/test_peg_prompt_contracts.py \
  tests/test_memory_recall_layers.py tests/test_provider_health.py tests/test_sessions_cli.py \
  tests/test_outcome_reflection.py tests/test_task_orchestrator_handoff.py tests/test_five_reports_f6.py -q

# 外部 Agent 五报告（PR-X1–X6 + M 后续）
PYTHONPATH=. pytest tests/test_external_agent_x1_x2.py tests/test_external_agent_x5_x6.py \
  tests/test_external_agent_m_confirm.py tests/test_external_agent_m_followup.py \
  tests/test_external_agent_p1_p4.py tests/test_message_ir.py tests/test_mcp_deferred.py \
  tests/test_p2_workflow_permissions.py tests/test_gateway_handler.py -q
```

运维速查：[`docs/guides/external-agent-reports-capabilities-2026-05.md`](docs/guides/external-agent-reports-capabilities-2026-05.md)
```

### 两套 Hook（不要混用）

| 机制 | 配置 | 适用 |
|------|------|------|
| **Shell hooks（CC 协议）** | `hooks.yaml` / `config.yaml` 的 `hooks:` | 运维脚本、审计、与 Claude Code 配置复用 |
| **进程内 hooks** | `butler/gateway/hooks.py` 的 `register_hook` | 低延迟拼上下文、`pre_gateway_dispatch` 改写 |

Shell hooks 示例：`butler/hooks/hooks.yaml.example`

| 事件 | 触发时机 |
|------|----------|
| `PreToolUse` / `PostToolUse` | 工具调用前后 |
| `UserPromptSubmit` | Gateway/CLI 消息进 LLM 前（`exit 2` 拦截） |
| `PermissionDenied` | 规划模式 / Hook 拦截 / 路径拒绝 |
| `SessionStart` | `/新对话` 清空后 |
| `SessionEnd` | 会话销毁前（`reason`: `clear` / `finalize` / `shutdown` / `end`） |
| `Stop` | 单轮 AgentLoop 结束（`matcher` 匹配 `status`；可注入 `additionalContext` 到 `diagnostics.stop_hook_context`） |
| `SubagentStart` | `delegate_task` 启动子代理前（`matcher` 匹配 `role`；上下文注入委派 prompt） |

`/诊断` 会显示 **Shell hooks 配置** 与 **最近执行**（退出码 + 摘要）；委派与 Stop 注入另有单行摘要。

### Gateway 长任务完成提醒（出站层，非 Notification hook）

微信 Gateway 在「已发过进度 ack」或耗时超过阈值时，可额外推送一条完成消息（与主回复分开）：

| 时机 | 条件 | 内容 |
|------|------|------|
| 委派结束 | `delegate_task` 完成/失败 | `AgentReport` 微信摘要 |
| 工作流结束 | `run_workflow` 完成 | 缓存的工作流报告 |
| 整轮结束 | 主回复已发送且曾发过 ack | 简短「本轮已完成」 |
| 入站队列 drain | 主回复已发且 `BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE=1` | 排队消息经 `schedule_supplementary_reply` **单独一条**（非拼进主回复） |

环境变量：`BUTLER_GATEWAY_COMPLETION_NOTIFY`（总开关）、`BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS`（默认 90）、`BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY`、`BUTLER_GATEWAY_TURN_COMPLETION_NOTIFY`、`BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY`。

完成推送与 `runtime` 定时推送共用 `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` 冷却；`BUTLER_GATEWAY_DURABLE_OUTBOX=1` 时会先写 `~/.butler/gateway_outbox/{pending,sent,failed}` 再发送，**用于本地留痕/审计，不替代重试队列**。发送失败（含限流/网络）时写入 `runtime/push_queue.jsonl`，由 `drain_push_queue` / runtime due 重试。工作流异常结束也会尝试推送失败摘要。

委派完成推送模式：`BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE`（默认 `last` 仅最后一次委派；`each` 最多 `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` 次；`once` 仅第一次）。Gateway 处理超时且曾发 progress ack 时可推 `BUTLER_GATEWAY_TIMEOUT_COMPLETION_NOTIFY`。Shell hooks：`SubagentStop` 在委派结束触发。

`/诊断` 另含 **出站推送本轮**（成功/失败/入队）与 **推送队列待发** 条数；`/新对话` 会重置 hook 与出站遥测。变量模板见仓库根 [`.env.example`](.env.example)；运维说明见 [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md)。真机步骤见上节 **H1–H10** 表。
