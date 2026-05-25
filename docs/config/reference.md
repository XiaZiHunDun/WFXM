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
| `BUTLER_COMPACTION_USE_TURNS` | 1 | 按 user turn + token 预算选压缩尾（OpenCode compaction.ts） |
| `BUTLER_COMPACTION_TAIL_TURNS` | 2 | 参与尾保护的最近 turn 数 |
| `BUTLER_COMPACTION_PRESERVE_RECENT_TOKENS` | 0 | 固定尾 token 预算（0=用 ratio） |
| `BUTLER_COMPACTION_PRESERVE_RECENT_RATIO` | 0.25 | 尾预算占有效上下文比例（2k–8k 钳制） |
| `BUTLER_COMPACTION_SPLIT_TURN` | 1 | 单 turn 超预算时 mid-turn 切分 |
| `BUTLER_COMPACTION_EXPLICIT_TURN` | 1 | 超阈值时 Loop 先跑一轮专用压缩（transcript `compaction_turn`） |
| `BUTLER_COMPACTION_TURN_MIN_MSGS` | 8 | 显式压缩 turn 最少消息数 |
| `BUTLER_POST_EDIT_FORMAT` | 0 | `1` 时 write_file/patch 后尝试 ruff/prettier |
| `BUTLER_POST_EDIT_FORMAT_TIMEOUT` | 30 | 格式化子进程超时（秒） |
| `BUTLER_PERMISSION_ONCE_TTL` | 300 | `/批准一次` 有效期（秒） |
| `BUTLER_DOOM_LOOP_THRESHOLD` | 3 | 连续相同 tool+args 拦截（0=关） |
| `BUTLER_DOOM_LOOP_MODE` | block | `ask` 时走 Owner `/批准一次`（permission `doom_loop`） |
| `BUTLER_TRANSCRIPT_REVERT_KEEP_LINES` | 40 | `/回滚` 默认保留 transcript 行数 |
| `BUTLER_PROJECT_WORKTREE` | 0 | `1` 且 `project.yaml` 含 `worktree:` 时工具 cwd 指向 worktree |
| `BUTLER_DELEGATE_ASYNC` | 1 | 微信 gateway 下 `delegate_task` 后台执行并单独推送完成摘要 |
| `BUTLER_TRANSCRIPT_EXPORT_MAX_LINES` | 500 | `/导出` 大文件时最多写入的行数 |
| `BUTLER_EXPORT_SEND_WECHAT_FILE` | 1 | `/导出` 成功后微信附带发送 `.md`（仅允许 exports 目录） |
| `BUTLER_EXPORT_SEND_WECHAT_MAX_BYTES` | 5242880 | 微信附件大小上限（5MB 默认） |
| `BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY` | 1 | 委派完成微信提醒（见 `BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE`） |
| `BUTLER_INSTRUCTION_WALKUP*` | 见 example | read_file 后注入邻近 AGENTS.md |
| `BUTLER_SESSION_TODOS` | 1 | 会话 `todos.json`；`/待办`；工具 `session_todos_list` / `session_todos_write`；项支持 `priority`: high/medium/low |
| `BUTLER_SESSION_TODOS_MAX_ITEMS` | 30 | 单会话待办条数上限（1–100） |
| `BUTLER_MCP_ENABLED` | 0 | 薄 MCP Client；需 `butler-system[mcp]` |
| `BUTLER_MCP_CONFIG` | `~/.butler/mcp.yaml` | MCP Server 列表（全局层） |
| （项目） | `<workspace>/.butler/mcp.yaml` | 项目层；与全局合并，**同名 server 以后者为准**（顺序：项目 → `BUTLER_MCP_CONFIG` → `~/.butler/mcp.yaml`） |
| `BUTLER_MCP_MAX_SERVERS` | 3 | 同时连接 Server 数 |
| `BUTLER_MCP_MAX_TOOLS` | 20 | 注入模型的 MCP 工具总数 |
| `BUTLER_MCP_TOOL_PREFIX` | mcp | 注册工具名前缀 |
| `BUTLER_MCP_STDIO_ALLOW_COMMANDS` | python,python3,uvx | stdio 可执行命令白名单 |
| `BUTLER_MCP_HTTP_HOSTS_ALLOW` | 空 | 额外允许的 HTTP Host |
| `BUTLER_MCP_SESSION_SCOPED` | 1 | 按 `session_key` 隔离连接 |
| `BUTLER_MCP_HTTP_ALLOW_PRIVATE` | 0 | 是否允许 127.0.0.1 等内网 Host |
| `BUTLER_SKILL_REGISTRY` | 1 | Skill 目录搜索/安装 |
| `BUTLER_SKILL_REGISTRY_SOURCES` | bundled,project,github,url,clawhub,marketplace,lobehub | 启用的技能源 |
| `BUTLER_REGISTRY_PENDING_TTL` | 1800 | 微信待确认安装过期秒数 |
| `BUTLER_REGISTRY_AUTO_INSTALL` | 0 | `1` 时跳过 community 源确认 |
| `BUTLER_LOBEHUB_ENABLED` | 1 | LobeHub 市场适配器 |
| `BUTLER_LOBEHUB_TOKEN` | — | LobeHub API Bearer（搜索/下载 ZIP） |
| `BUTLER_LOBEHUB_URL` | https://market.lobehub.com | LobeHub API 根 |
| `BUTLER_LOBEHUB_USE_CLI` | 0 | `1` 时优先 `npx @lobehub/market-cli` |
| `BUTLER_LOBEHUB_LOCALE` | zh-CN | 搜索 locale |
| `BUTLER_CLAUDE_MARKETPLACE_ENABLED` | 1 | Claude `marketplace.json` 适配器 |
| `BUTLER_CLAUDE_MARKETPLACE_URLS` | 空 | 远程 marketplace.json URL（CSV，需 SSRF 安全） |
| `BUTLER_CLAWHUB_ENABLED` | 1 | ClawHub community 源 |
| `BUTLER_CLAWHUB_URL` | https://clawhub.ai/api/v1 | ClawHub API 根路径 |
| `BUTLER_REGISTRY_CACHE_TTL` | 3600 | 远程技能索引（ClawHub 等）缓存秒数 |
| `BUTLER_SKILL_TRUSTED_REPOS` | 空 | 可信 GitHub `owner/repo` CSV |
| `BUTLER_SKILL_INSTALL_MAX_MB` | 2 | 单技能安装体积上限 |
| `BUTLER_MCP_CATALOG` | 1 | MCP 目录 `butler mcp add` |
| `BUTLER_MCP_CATALOG_URLS` | 空 | 远程 MCP catalog JSON/YAML URL（CSV，SSRF 校验；与内置 catalog 合并，同名以内置为准） |
| （CLI） | — | `butler mcp add <id> --workspace <dir>` 写入项目 `.butler/mcp.yaml`；`--global` 强制全局；probe 失败不写 yaml |
| `BUTLER_MCP_AUTO_PROJECT_TOOLS` | 1 | 项目层 MCP 安装后自动向 `project.yaml` tools 追加 `mcp_*`（仅当 tools 非空且尚无 mcp 项） |
| `GITHUB_TOKEN` | — | GitHub API（技能拉取） |
| `BUTLER_SESSION_TRANSCRIPT` | 1 | `~/.butler/sessions/<key>/transcript.jsonl`；含 compact / `bot_loop_suppressed` 等事件 |
| `BUTLER_SESSION_TRANSCRIPT_MAX_BYTES` | 52428800 | transcript 轮转阈值 |
| `BUTLER_READ_BEFORE_EDIT` | 1 | patch/write 前须 read_file + mtime |
| `BUTLER_READ_STATE_MAX_ENTRIES` | 100 | read state LRU 上限 |
| `BUTLER_DISABLE_AUTO_COMPACT` | 0 | `1` 关闭 LLM 摘要压缩 |
| `BUTLER_CONTEXT_*` | — | 压缩阈值等（见 `.env.example`） |
| `BUTLER_STREAMING_TOOLS` | 1 | 流式只读工具参数完整后预执行 |
| `BUTLER_CACHE_SAFE_DELEGATE` | 1 | 委派子 loop 共享父 system + tools/messages 指纹（v2） |
| `BUTLER_CACHE_SAFE_SHARED_CHARS` | 4096 | 共享 system 前缀最大字符 |
| `BUTLER_CACHE_SAFE_MESSAGES_CHARS` | 2048 | 共享 messages 前缀用于 cache 指纹 |
| `BUTLER_TURN_BUDGET_MAX_CONTINUATIONS` | 3 | 回合内 token 预算续跑次数 |
| `BUTLER_TURN_BUDGET_MIN_DELTA` | 500 | 续跑收益递减：Δ tokens 低于此则停 |
| `BUTLER_PREEMPTIVE_COMPACT` | 1 | LLM 前估算 → compact / truncate / overflow_fail |
| `BUTLER_PREEMPTIVE_TRUNCATE_BUFFER` | 512 | 截断后仍允许的 token 缓冲 |
| `BUTLER_POST_COMPACT_AGENTS_SECTIONS` | Session Startup,Red Lines,… | 压缩后回灌 AGENTS.md 节名 |
| `BUTLER_POST_COMPACT_AGENTS_MAX_CHARS` | 2000 | 上述节总字符上限 |
| `BUTLER_TOOL_LOOP_DETECTORS` | ping_pong,poll,circuit | 工具环检测（`off` 关闭） |
| `BUTLER_TOOL_LOOP_CIRCUIT_LIMIT` | 40 | 单轮工具调用熔断上限 |
| `BUTLER_TERMINAL_REQUIRE_APPROVAL` | 0 | `1` 时 terminal 须 Owner `/批准执行` |
| `BUTLER_OUTBOUND_BLOCK_DELAY_MS` | 0 | 微信多分块出站随机间隔（未设则用 `WECHAT_SEND_CHUNK_DELAY_SECONDS`） |
| `BUTLER_TRANSCRIPT_INDEX_MIN_BYTES` | 262144 | transcript 大于此值启用尾索引 |
| `BUTLER_HOOK_FAIL_CLOSED` | 0 | `1` 时 PreToolUse 非 0 退出即阻断工具 |

> OpenCode 对标运维速查：[`guides/opencode-parity.md`](../guides/opencode-parity.md)  
> OpenClaw 对标详表：[`plans/openclaw-learning-plan-2026-05.md`](../plans/openclaw-learning-plan-2026-05.md)

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
| `BUTLER_REPLY_ADMISSION` | 1 | 每 session 单飞 reply turn；忙则入队 |
| `BUTLER_BOT_LOOP_GUARD` | 0 | 群聊 bot 互 @ 环防护 |
| `BUTLER_BOT_LOOP_PAIR_THRESHOLD` | 6 | bot 环滑动窗口阈值 |
| `BUTLER_STREAM_MEMORY_SCRUB` | 1 | 流式 delta 剔除 `<memory-context>` 块 |
| `BUTLER_GATEWAY_STREAM_PREVIEW` | 0 | 长任务 ack 附带流式预览片段（非 iLink 消息编辑） |
| `BUTLER_AUTO_CONTINUE` | 1 | 中断后「继续」在 freshness 窗内恢复任务 |
| `BUTLER_AUTO_CONTINUE_MAX_AGE` | 3600 | auto-continue 待办有效期（秒） |
| `BUTLER_TOOL_RETRY` | 1 | 瞬态错误工具自动重试 |
| `BUTLER_TOOL_CALL_LIMIT_PER_TOOL` | 0 | 每轮单工具调用上限（0=关闭） |
| `BUTLER_OUTBOUND_PII_SCRUB` | 1 | 微信出站手机号/证件号脱敏 |
| `BUTLER_GATEWAY_HUMAN_GATE_TTL` | 3600 | workflow 人工 gate 最短 60s 过期 |
| `BUTLER_DELEGATE_MAX_ITERATIONS` | 24 | 委派子 loop 默认迭代上限 |
| `BUTLER_CATALOG_INTEGRITY` | 1 | bundled catalog SHA-256 校验 |
| `BUTLER_TERMINAL_DANGER_CHECK` | 1 | terminal 危险命令模式阻断 |
| `BUTLER_TOOL_SELECTOR` | 1 | 工具数超阈值时按上下文缩小 schema |
| `BUTLER_TOOL_RESULT_CACHE` | 1 | 只读工具结果会话内短 TTL 缓存 |
| `BUTLER_COMPACTION_USE_HERMES_TEMPLATE` | 0 | 压缩摘要使用 Hermes v2 节结构 |
| `BUTLER_GATEWAY_PROGRESSIVE_STREAM` | 0 | 长流式任务渐进式微信补充消息 |
| `BUTLER_EXECUTE_CODE` | 0 | 启用 `execute_code` 沙箱工具（须安全评审） |
| `BUTLER_SECRETS_FILE` | 1 | 从 `~/.butler/secrets.yaml` 加载 provider API key |
| `BUTLER_TERMINAL_SMART_APPROVE` | 1 | `/批准模式 <pattern>` 本会话放行危险 terminal |
| `BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST` | — | 向后剪枝最少回收字符数 |
| `BUTLER_BOT_LOOP_WHITELIST` | — | 逗号分隔 chat_id 白名单 |
| `BUTLER_TURN_TOKEN_BUDGET` | 1 | 句末 `+500k` / `/budget` 提高迭代上限 |
| `BUTLER_TURN_BUDGET_*` | — | 预算数值（见 example） |

Shell Stop 钩子：`exit 2` 或 JSON `decision:block` → **循环内**注入 user 消息并续跑（`stop_hook_blocked`），非仅替换最终回复。

**P2 工作流权限**（`.butler/permissions.yaml`）：`workflow_steps.<step_id>.tools` 限制 DAG 节点内工具；`requires_approval: true` 的步骤需微信「确认」后再次 `/workflow <name>`。命令：`/确认`、`/取消`。

项目权限：`.butler/permissions.yaml` 或 `project.yaml` 的 `permissions.rules`（`allow`/`deny`/`ask`，**后写规则覆盖前写**，无 LLM classifier）。`external_directory` 节控制工作区外路径；Owner 微信 **`/批准一次`**、**`/始终允许 <权限>`**、**`/权限`** 写入 `~/.butler/sessions/<session_key>/approvals.json`。`delegate_subagent` 节控制委派子 loop 工具白名单；委派子 loop 使用 `child_session_key` 独立 transcript（`{session}::delegate::{task_id}`）。

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
