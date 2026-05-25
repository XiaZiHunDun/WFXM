# Butler 配置参考（env + YAML）

> **原则**：`.env` 仅放**密钥与部署覆盖**；稳定行为默认值优先写入 `~/.butler/config.yaml`（见 [`config.yaml.example`](config.yaml.example)）。  
> 完整密钥示例：仓库根 `.env.example`。

## 推荐：`config.yaml` vs `.env`

| 放 `~/.butler/config.yaml` | 放 `.env`（或环境） |
|---------------------------|---------------------|
| `default_provider`、`butler_name`、`owner_name` | `MINIMAX_API_KEY`、`DEEPSEEK_API_KEY` 等 |
| `models.butler` / `dev_agent` / `content_agent` / `review_agent` | `WECHAT_TOKEN`、`WECHAT_ACCOUNT_ID` |
| `auxiliary.compression` / `post_session` | `BUTLER_OWNER_WECHAT_ID`、`WECHAT_ALLOWED_USERS` |
| `gateway.inbound_media`（识图/STT 开关与模型名） | `BUTLER_PROJECTS_DIR`、`BUTLER_TOOL_SAFE_ROOT`（部署路径） |
| — | `BUTLER_RUNTIME_*` 运维开关（可逐步迁 YAML，当前以 env 为主） |

安装：`bash scripts/setup-butler-config.sh` 从 example 生成；`/model save` 会更新 `models` 段且不覆盖 `gateway`/`auxiliary`。

## 必填（至少一项）

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY` 等 | LLM Provider（见 `.env.example`） |

## 微信网关（生产建议）

| 变量 | 默认 | 说明 |
|------|------|------|
| `WECHAT_TOKEN` / `WECHAT_ACCOUNT_ID` | — | iLink 绑定（`butler wechat-setup`） |
| `WECHAT_DM_POLICY` | open | 生产建议 `allowlist` |
| `WECHAT_ALLOWED_USERS` | — | 逗号分隔微信 user id |
| `BUTLER_OWNER_WECHAT_ID` | — | Owner；runtime 推送、**/项目 新建** 白名单 |
| `BUTLER_PROJECT_CREATE_OPEN` | 0 | `1` 跳过 Owner 新建校验（仅开发） |
| `BUTLER_DEFAULT_PROJECT` | — | 未绑 chat 时的默认项目名 |
| `BUTLER_GATEWAY_HANDLER_TIMEOUT` | 600 | 单条消息处理超时（秒） |
| `BUTLER_GATEWAY_HANDLER_WORKERS` | 2 | 并发 worker 数 |

## 项目与工具安全

| 变量 | 说明 |
|------|------|
| `BUTLER_PROJECTS_DIR` | 项目根（默认仓库 `projects/`） |
| `BUTLER_TOOL_SAFE_ROOT` | 工具路径沙箱根 |
| `BUTLER_LEAD_PROJECTS` | 厂长模式项目列表（逗号分隔；可被 `project.yaml` `lead: true` 补充） |
| `BUTLER_ENABLE_TERMINAL` | `1` 启用 terminal |
| `BUTLER_ENABLE_GIT` / `BUTLER_ENABLE_GIT_WRITE` | 只读 / 写 git 工具 |

## Runtime

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_RUNTIME_ENABLED` | 1 | 总开关 |
| `BUTLER_RUNTIME_PUSH` | 1 | 结果推微信 |
| `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` | 25 | 推送间隔 |
| `BUTLER_RUNTIME_FAIL_ALERT_STREAK` | 3 | 连续失败告警 |
| `BUTLER_RUNTIME_SMOKE_PUSH` | 0 | 冒烟是否真推送 |

## 记忆

| 变量 | 说明 |
|------|------|
| `BUTLER_SEMANTIC_MEMORY` | `1` 启用本地向量 |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | `0` 不把每轮聊天写入 experience |
| `BUTLER_QUEUE_PREFETCH` | `1` 推荐：下轮预取缓存 |
| `BUTLER_PREFETCH_*` | 预取字符上限与条数（见 `.env.example`） |

## Agent Loop 线束（上下文 / 安全）

> 设计说明：[`plans/cc-butler-gap-analysis-2026-05.md`](../plans/cc-butler-gap-analysis-2026-05.md) · [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_TOOL_RESULT_SPILL` | 1 | 超大 tool 结果落盘，上下文为 `<persisted-output>` |
| `BUTLER_TOOL_RESULT_SPILL_MIN_CHARS` | 8192 | 默认单条落盘阈值（≥256） |
| `BUTLER_TOOL_RESULT_THRESHOLDS` | — | JSON 按工具名覆盖阈值；`read_file` 等默认不落盘 |
| `BUTLER_TOOL_RESULT_MESSAGE_BUDGET` | 1 | 单轮 tool 结果总字符预算（CC enforceToolResultBudget） |
| `BUTLER_TOOL_RESULT_MESSAGE_MAX_CHARS` | 200000 | 单轮 tool 结果聚合上限 |
| `BUTLER_TOOL_PRUNE_*` | 见 example | 按工具分级 micro 剪枝 |
| `BUTLER_TOOL_PRUNE_BACKWARD*` | 见 example | OpenCode 式从旧 tool 消息向后擦除输出 |
| `BUTLER_COMPACTION_USE_OPENCODE_TEMPLATE` | 1 | 压缩摘要使用 Goal/Progress/… 固定节 |
| `BUTLER_DOOM_LOOP_THRESHOLD` | 3 | 连续相同 tool+args 拦截（0=关） |
| `BUTLER_INSTRUCTION_WALKUP*` | 见 example | read_file 后注入邻近 AGENTS.md |
| `BUTLER_SESSION_TODOS` | 1 | 会话 `todos.json` replace-all；`/待办` |
| `BUTLER_SESSION_TRANSCRIPT` | 1 | 含 `compact_scheduled` / `compact_done` 事件 |
| `BUTLER_READ_BEFORE_EDIT` | 1 | patch/write 前须 read_file + mtime |
| `BUTLER_READ_STATE_MAX_ENTRIES` | 100 | read state LRU 上限 |
| `BUTLER_SESSION_TRANSCRIPT` | 1 | `~/.butler/sessions/<key>/transcript.jsonl` |
| `BUTLER_SESSION_TRANSCRIPT_MAX_BYTES` | 52428800 |  transcript 轮转阈值 |
| `BUTLER_DISABLE_AUTO_COMPACT` | 0 | `1` 关闭 LLM 摘要压缩 |
| `BUTLER_CONTEXT_*` | — | 压缩阈值等（见 `.env.example`） |
| `BUTLER_STREAMING_TOOLS` | 1 | 流式只读工具参数完整后预执行 |
| `BUTLER_CACHE_SAFE_DELEGATE` | 1 | 委派子 loop 共享父 system + tools/messages 指纹（v2） |
| `BUTLER_CACHE_SAFE_SHARED_CHARS` | 4096 | 共享 system 前缀最大字符 |
| `BUTLER_CACHE_SAFE_MESSAGES_CHARS` | 2048 | 共享 messages 前缀用于 cache 指纹 |
| `BUTLER_TURN_BUDGET_MAX_CONTINUATIONS` | 3 | 回合内 token 预算续跑次数 |
| `BUTLER_TURN_BUDGET_MIN_DELTA` | 500 | 续跑收益递减：Δ tokens 低于此则停 |

## Gateway 线束（入站 / 出站）

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_GATEWAY_MESSAGE_QUEUE` | 1 | 忙会话非斜杠消息入队 |
| `BUTLER_GATEWAY_QUEUE_MODE` | followup | 全局队列模式：followup / collect / interrupt / steer；会话可用 `/queue` 覆盖 |
| `BUTLER_GATEWAY_QUEUE_CAP` | 20 | 每会话队列上限 |
| `BUTLER_GATEWAY_QUEUE_DROP` | summarize | 溢出策略：summarize / old / new |
| `BUTLER_GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS` | 500 | collect 模式 debounce（预留；drain 时合并） |
| `BUTLER_GATEWAY_QUEUE_DRAIN_PER_TURN` | 1 | 每轮最多 drain 条数（collect 模式合并为一条） |
| `BUTLER_GATEWAY_QUEUE_PUSH_VIA_BRIDGE` | 1 | drain 正文单独微信（非拼主回复） |
| `BUTLER_GATEWAY_COMPLETION_NOTIFY` | 1 | 长任务完成额外推送总开关 |
| `BUTLER_GATEWAY_DELEGATE_COMPLETION_*` | — | 委派完成推送模式（见 `.env.example`） |
| `BUTLER_TURN_TOKEN_BUDGET` | 1 | 句末 `+500k` / `/budget` 提高迭代上限 |
| `BUTLER_TURN_BUDGET_*` | — | 预算数值（见 example） |

Shell Stop 钩子：`exit 2` 或 JSON `decision:block` → **循环内**注入 user 消息并续跑（`stop_hook_blocked`），非仅替换最终回复。

**P2 工作流权限**（`.butler/permissions.yaml`）：`workflow_steps.<step_id>.tools` 限制 DAG 节点内工具；`requires_approval: true` 的步骤需微信「确认」后再次 `/workflow <name>`。命令：`/确认`、`/取消`。

项目权限：`.butler/permissions.yaml` 或 `project.yaml` 的 `permissions.rules`（`allow`/`deny`/`ask`，**后写规则覆盖前写**，无 LLM classifier）。`delegate_subagent` 节控制委派子 loop 工具白名单。

运维与 H1–H10 见 [`guides/wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md)。

## 冒烟 / 开发

| 变量 | 说明 |
|------|------|
| `BUTLER_WECHAT_DEV_SMOKE` | `/诊断` 显示开发项 |
| `BUTLER_CLI_STREAM_MODE` | CLI 流式 `live` / `off` |
| `BUTLER_RUNTIME_RUN_CONSISTENCY` | `1` 时 runtime-smoke 跑 consistency-weekly |

## 工具名别名（`project.yaml` / 提示词 → 注册表）

| 文档或 yaml 中写法 | 注册表 canonical |
|-------------------|------------------|
| `edit_file` | `patch` |
| `search_code` | `search_files` |
| `run_shell` | `terminal` |
| `skill_list` | `skills_list` |

Lead 厂长模式另禁 `patch` / `terminal` / `write_file`，保留 `delegate_task`、`read_file`、`run_workflow` 等 — 见 [`architecture/project-lead-decision.md`](../architecture/project-lead-decision.md)。

## 相关

- [`../guides/project-onboarding.md`](../guides/project-onboarding.md)  
- [`../plans/consolidation-2026-05.md`](../plans/consolidation-2026-05.md)
