# Butler 配置参考（env + YAML）

> **原则**：`.env` 仅放**密钥与部署覆盖**；稳定行为默认值优先写入 `~/.butler/config.yaml`（见 [`config.yaml.example`](config.yaml.example)）。  
> 完整密钥示例：仓库根 `.env.example`。

## 推荐：`config.yaml` vs `.env`

| 放 `~/.butler/config.yaml` | 放 `.env`（或环境） |
|---------------------------|---------------------|
| `default_provider`、`butler_name`、`owner_name` | `MINIMAX_API_KEY`、`DEEPSEEK_API_KEY` 等 |
| `models.butler` / `dev_agent` / `content_agent` / `review_agent` | `WECHAT_TOKEN`、`WECHAT_ACCOUNT_ID` |
| `auxiliary.compression` / `post_session` | `BUTLER_OWNER_WECHAT_ID`、`WECHAT_ALLOWED_USERS`、`BUTLER_GATEWAY_ALLOWLIST` |
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
| `BUTLER_GATEWAY_ALLOWLIST` | — | 历史兼容 fallback allowlist；仅在未设 `BUTLER_OWNER_WECHAT_ID` 且未设 `WECHAT_ALLOWED_USERS` 时供 runtime push 与 Owner gate 使用；不影响 DM 入站 allowlist |
| `BUTLER_PROJECT_CREATE_OPEN` | 0 | `1` 跳过 Owner 新建校验（仅开发） |
| `BUTLER_DEFAULT_PROJECT` | — | 未绑 chat 时的默认项目名 |
| `BUTLER_GATEWAY_HANDLER_TIMEOUT` | 600 | 单条消息处理超时（秒） |
| `BUTLER_GATEWAY_HANDLER_WORKERS` | 2 | 并发 worker 数 |
| `BUTLER_GATEWAY_MAX_SESSIONS` | 50 | 最大活跃会话数 |
| `BUTLER_GATEWAY_SESSION_IDLE_TTL_SECONDS` | 7200 | 会话空闲过期（秒） |
| `BUTLER_GATEWAY_TYPING_ENABLED` | 1 | 输入状态提示 |
| `BUTLER_GATEWAY_PROGRESS_ACK_ENABLED` | 1 | 长任务进度确认推送 |
| `BUTLER_GATEWAY_PROGRESS_ACK_SECONDS` | 30 | 进度确认间隔（秒） |
| `BUTLER_GATEWAY_TIMEOUT_COMPLETION_NOTIFY` | 1 | 超时完成推送 |
| `BUTLER_GATEWAY_TURN_COMPLETION_NOTIFY` | 1 | 轮次完成推送 |
| `BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY` | 1 | 工作流完成推送 |
| `BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS` | 10 | 完成推送最短等待时间 |
| `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` | 500 | 委派完成推送单条最大字符 |

## 项目与工具安全

| 变量 | 说明 |
|------|------|
| `BUTLER_PROJECTS_DIR` | 项目根（默认仓库 `projects/`） |
| `BUTLER_TOOL_SAFE_ROOT` | 工具路径沙箱根 |
| `BUTLER_LEAD_PROJECTS` | 厂长模式项目列表（逗号分隔；可被 `project.yaml` `lead: true` 补充） |
| `BUTLER_HOME` | `~/.butler` | Butler 数据根目录 |
| `BUTLER_ENABLE_TERMINAL` | `1` 启用 terminal |
| `BUTLER_TERMINAL_ALLOWLIST_EXTRA` | — | 额外允许的 terminal 命令（逗号分隔） |
| `BUTLER_TERMINAL_PROFILE` | — | 终端 profile 名（不同项目可用不同白名单） |
| `BUTLER_ENABLE_GIT` / `BUTLER_ENABLE_GIT_WRITE` | 只读 / 写 git 工具 |
| `BUTLER_ENABLE_GIT_PUSH` | `1` 启用 `git_push` 工具（需同时 `GIT_WRITE=1`；push 前需 Owner 审批） |

## 日志

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_LOG_LEVEL` | INFO | 日志级别（DEBUG / INFO / WARNING / ERROR）；CLI 和 Gateway 统一读取 |

## Runtime

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_RUNTIME_ENABLED` | 1 | 总开关 |
| `BUTLER_RUNTIME_PUSH` | 1 | 结果推微信 |
| `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` | 25 | 推送间隔 |
| `BUTLER_RUNTIME_FAIL_ALERT_STREAK` | 3 | 连续失败告警 |
| `BUTLER_RUNTIME_SMOKE_PUSH` | 0 | 冒烟是否真推送 |
| `BUTLER_RUNTIME_PUSH_QUEUE` | 1 | 推送入队开关 |

## 记忆

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_SEMANTIC_MEMORY` | 1 | 启用本地向量 |
| `BUTLER_SEMANTIC_SEARCH_LIMIT` | 5 | 单次语义搜索返回条数 |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | 0 | 不把每轮聊天写入 experience |
| `BUTLER_QUEUE_PREFETCH` | 1 | 推荐：下轮预取缓存 |
| `BUTLER_PREFETCH_CACHE_TTL` | 120 | 预取缓存 TTL（秒） |
| `BUTLER_PREFETCH_MAX_CHARS` | 4000 | 单层预取字符上限 |
| `BUTLER_PREFETCH_TOTAL_MAX_CHARS` | 12000 | 全部预取合计字符上限 |
| `BUTLER_PREFETCH_PROJECT_HITS` | 5 | 项目层预取条数 |
| `BUTLER_PREFETCH_PROJECT_MAX_CHARS` | 3000 | 项目层预取字符上限 |
| `BUTLER_PREFETCH_EXPERIENCE_HITS` | 5 | 经验层预取条数 |
| `BUTLER_PREFETCH_FACTS_MAX_CHARS` | 2000 | 事实预取字符上限 |
| `BUTLER_MEMORY_RECALL_LAYERS` | — | 逗号分隔记忆检索层（project,experience,fact） |
| `BUTLER_MEMORY_ACCESS_BOOST` | 0.1 | 记忆访问频率权重加成 |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | 30 | 记忆衰减半衰期（天） |
| `BUTLER_MEMORY_PRIVATE_TAGS` | — | 逗号分隔私有标签 |
| `BUTLER_MEMO_ENABLED` | 1 | 0=关闭备忘录模块（memo_add/list/search/update/delete 工具） |
| `BUTLER_MEMO_MAX_ACTIVE` | 200 | 活跃备忘条数上限 |
| `BUTLER_CONTACTS_ENABLED` | 1 | 0=关闭通讯录模块（contact_add/find/update/delete/list 工具） |
| `BUTLER_EXPENSE_ENABLED` | 1 | 0=关闭记账模块（expense_add/summary/list/delete 工具） |
| `BUTLER_HABITS_ENABLED` | 1 | 0=关闭习惯打卡模块（habit_create/checkin/stats/list/delete 工具） |
| `BUTLER_FTS_HYBRID_WEIGHT` | 0.3 | 全文/向量混合检索权重 |
| `BUTLER_VECTOR_HYBRID_WEIGHT` | 0.7 | 向量检索在混合中的权重 |
| `BUTLER_EMBEDDING_PROVIDER` | local | 嵌入提供者：local/fastembed/openai/minimax |
| `BUTLER_EMBEDDING_MODEL` | hashing-v1 | 嵌入模型名 |

## Agent Loop 线束（上下文 / 安全）

> 设计说明：[`plans/cc-butler-gap-analysis-2026-05.md`](../plans/active/cc-butler-gap-analysis-2026-05.md) · [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_TOOL_RESULT_SPILL` | 1 | 超大 tool 结果落盘，上下文为 `<persisted-output>` |
| `BUTLER_TOOL_RESULT_INJECT_ONCE` | 1 | 落盘结果首轮完整注入，后续 API 轮仅 `<persisted-output-ref>`+摘要 |
| `BUTLER_MARKDOWN_CHUNKING` | 1 | reindex 时按标题树切分 MEMORY/DESIGN/AGENTS 等 Markdown |
| `BUTLER_MARKDOWN_CHUNK_MIN_CHARS` | 256 | 切块最小字符（过小段落会合并） |
| `BUTLER_MARKDOWN_CHUNK_MAX_CHARS` | 4000 | 单块最大字符 |
| `BUTLER_MARKDOWN_HEADING_BOOST` | 0.18 | 检索 query 与 `[headings: …]` 重合时的分数加成系数 |
| `BUTLER_MARKDOWN_INDEX_PATHS` | 见下 | 逗号分隔或 JSON 数组；默认 MEMORY/DESIGN/AGENTS/架构 doc |
| `BUTLER_BATCH_STALE_GUARD` | 1 | 同批 `patch`/`write_file` 成功后跳过后续过时的 `read_file`/`grep` 等 |
| `BUTLER_TOOL_RESULT_SPILL_MIN_CHARS` | 8192 | 默认单条落盘阈值（≥256） |
| `BUTLER_TOOL_RESULT_THRESHOLDS` | — | JSON 按工具名覆盖阈值；`read_file` 等默认不落盘 |
| `BUTLER_TOOL_RESULT_MESSAGE_BUDGET` | 1 | 单轮 tool 结果总字符预算（CC enforceToolResultBudget） |
| `BUTLER_TOOL_RESULT_MESSAGE_MAX_CHARS` | 200000 | 单轮 tool 结果聚合上限 |
| `BUTLER_TOOL_RESULT_SPILL_PREVIEW_CHARS` | 500 | 落盘 tool 结果内联预览字符 |
| `BUTLER_TOOL_AUDIT_JSONL` | 0 | `1` 写入工具审计 JSONL |
| `BUTLER_TOOL_AUDIT_PATH` | — | 审计 JSONL 文件路径 |
| `BUTLER_TOOL_ERROR_POLICY` | log | 工具错误策略：log/raise/retry |
| `BUTLER_UTF16_SAFE_TRUNCATE` | 1 | 截断时对齐 UTF-16 边界 |
| `BUTLER_TOOL_PRUNE_DEFAULT_CHARS` | 600 | 默认工具输出剪枝字符 |
| `BUTLER_TOOL_PRUNE_PRESERVE_CHARS` | 2000 | 剪枝保护字符 |
| `BUTLER_TOOL_PRUNE_KEEP_RECENT` | 3 | 保留最近 N 个工具输出不剪枝 |
| `BUTLER_TOOL_PRUNE_CLEARABLE_CHARS` | 100 | 可完全清除的工具输出阈值 |
| `BUTLER_TOOL_PRUNE_*` | 见 example | 按工具分级 micro 剪枝 |
| `BUTLER_TOOL_PRUNE_BACKWARD` | 1 | OpenCode 式向后工具输出剪枝开关 |
| `BUTLER_TOOL_PRUNE_BACKWARD_MINIMUM` | 20000 | 向后剪枝目标最小字符 |
| `BUTLER_TOOL_PRUNE_BACKWARD_PROTECT` | 40000 | 向后剪枝保护字符 |
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
| `BUTLER_DOOM_LOOP_SOFT_NUDGE` | 1 | 达阈值前 1 次时 `warn`（`doom_loop_soft_nudge`），再重复才硬拦截 |
| `BUTLER_LOOP_BUDGET_NUDGE` | 1 | 迭代或 token 达 75% 时注入收尾提示 |
| `BUTLER_LOOP_BUDGET_WARN_RATIO` | 0.75 | 预算预警比例（迭代 `iteration/max_iterations` 或 token 用量） |
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
| `BUTLER_CONTEXT_OUTPUT_RESERVE` | 16384 | 压缩时为模型输出保留的 token 数 |
| `BUTLER_CONTEXT_COMPACT_RESERVE` | 32768 | 自动压缩触发缓冲 token |
| `BUTLER_CONTEXT_WARNING_BUFFER` | 4096 | 上下文 warning 阈值缓冲 |
| `BUTLER_CONTEXT_ERROR_BUFFER` | 2048 | 上下文 error 阈值缓冲 |
| `BUTLER_CONTEXT_BLOCKING_BUFFER` | 1024 | 上下文阻塞阈值缓冲 |
| `BUTLER_CONTEXT_COMPACT_MAX_FAILURES` | 3 | 连续压缩失败上限 |
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
| `BUTLER_POST_COMPACT_DESIGN_SECTIONS` | Overview,Do's and Don'ts,… | 压缩后回灌 DESIGN.md 节名 |
| `BUTLER_POST_COMPACT_DESIGN_MAX_CHARS` | 2500 | 上述 DESIGN 节总字符上限 |
| `BUTLER_DESIGN_CONTEXT_INJECT` | 1 | `0` 关闭 orchestrator 中 DESIGN 摘要注入 |
| `BUTLER_DESIGN_PRESET_DIR` | （空） | `design_preset` 解析参考目录（不打包进主仓库） |
| `BUTLER_EXPERIMENT_MODE` | 0 | `1` 时仅允许写入 `experiments/`；`.butler/harness/` 只读 |
| `BUTLER_EXPERIMENT_LEDGER` | 1 | runtime job 解析 `METRIC` 写入 `.butler/experiments.tsv` |
| `BUTLER_EXPERIMENT_GIT_RESET` | 0 | `1` 时 CLI `experiment discard --apply-reset` 可 `git reset --hard` |
| `BUTLER_EXPERIMENT_LOG_LINES` | 200 | job 输出超过行数写入 `.butler/last_run.log` |
| `BUTLER_RAG_SUBQUERY` | 1 | `0` 关闭复合问句多子 query 检索 |
| `BUTLER_RAG_SUBQUERY_MAX` | 3 | 单次检索最多子 query 数 |
| `BUTLER_RAG_SUBQUERY_MIN_CHARS` | 72 | 超过此长度才尝试按句切分 |
| `BUTLER_INSTRUCTION_WALKUP_MAX_CHARS` | 2000 | read_file 后注入 AGENTS.md 最大字符 |
| `BUTLER_TOOL_IMPLICIT_CONTEXT` | 1 | `0` 关闭 dispatch 时注入 `_butler_*` 隐式参数 |
| `BUTLER_SCHEMA_OPTIMIZE` | 1 | LLM 调用前预净化 tool schema |
| `BUTLER_TOKEN_COST_ESTIMATE` | 0 | `1` 时 `/诊断` 显示粗算美元成本 |
| `BUTLER_RESEARCH_SIMPLICITY_ANCHOR` | 1 | 压缩后回灌简洁性/实验纪律锚点 |
| `BUTLER_EXPERIMENT_CRASH_BLOCK` | 3 | 同假设连续 crash 达此次数时诊断提示阻断 |
| `BUTLER_OUTCOME_REFLECTION` | 1 | `0` 关闭 `.butler/outcomes.tsv` 与 orchestrator 反思注入 |
| ~~`BUTLER_WORKFLOW_HANDOFF_ONLY`~~ | — | **非环境变量**；workflow YAML 步骤字段 `handoff_only: true/false`（默认 true）控制依赖上下文模式 |
| `BUTLER_WORKFLOW_CLEAR_CHILD` | 0 | `1` 时 DAG/委派上行仅 headline+summary，不带子 Loop 全量轨迹 |
| `BUTLER_WORKFLOW_RESCUE` | 1 | `1` 时步骤失败且 YAML 含 `rescue_steps` 时跑补救子步骤 |
| `BUTLER_WORKFLOW_OPTIONAL` | 1 | `1` 时 `optional: true` 步骤失败不阻断依赖方（Ansible ignore_errors 子集） |
| `BUTLER_WORKFLOW_RUN_SNAPSHOT` | 1 | 写入 `.butler/workflow_runs/<workflow>-latest.json` |
| `BUTLER_COMPACT_SKILL_PRESERVE` | 1 | 压缩前保留最近 skill 读取 tool 对 |
| `BUTLER_SAFETY_FINISH_GUARD` | 1 | `content_filter` 等 finish_reason 时忽略 tool_calls |
| `BUTLER_FINISH_TOOL_TRUNCATE` | 1 | 同轮 `finish` 工具后截断多余 tool_calls |
| `BUTLER_MESSAGE_IR` | 1 | 入站经 Canonical Message IR 规范化 |
| `BUTLER_TOOL_WIRE` | 1 | 按 provider 适配 tool schema / tool_calls |
| `BUTLER_MCP_DEFERRED_TOOLS` | 0 | `1` 时 MCP 仅注入已 promote 工具 + `mcp_tool_search` / `load_mcp_tools` |
| `BUTLER_ASK_CLARIFICATION` | 1 | 启用 `ask_clarification` 工具（结束本轮追问） |
| `BUTLER_STATIC_SYSTEM_REMINDER` | 0 | `1` 时静态 system + 动态 `<system-reminder>` 进 user 轮 |
| `BUTLER_EXP_CACHE` | 0 | 无 tools 的 LLM 请求指纹缓存（`.butler/experiences/llm_cache.jsonl`） |
| `BUTLER_EXP_CACHE_MAX` | 500 | 经验缓存最大条数 |
| `BUTLER_EXP_CACHE_STORE` | 1 | 是否写入缓存 |
| `BUTLER_TOOL_RECALL_BM25` | 0 | 工具列表超阈值时用 BM25 召回 top-k |
| `BUTLER_OUTPUT_SCHEMA_VALIDATE` | 1 | workflow `output_schema` 结构化校验 |
| `BUTLER_WORKFLOW_CHECKPOINT` | 1 | 每步完成后写 `.butler/workflow_runs/<wf>-checkpoint.json` |
| `BUTLER_WORKFLOW_MAX_PARALLEL` | 空 | 全局 DAG 同层并发上限（可被 workflow YAML `max_parallel` 覆盖） |
| `BUTLER_TWO_PHASE_CONFIRM` | 0 | 高风险工具（terminal/delete_file）待 Owner `/确认工具` 后执行 |
| `BUTLER_PERMISSION_RISK_HEURISTIC` | 0 | 终端危险模式改为 ask + `/批准执行`（非硬阻断） |
| `BUTLER_OUTPUT_SCHEMA_REPAIR` | 1 | workflow 终局 schema 校验失败后一次 LLM 修复 |
| `BUTLER_INBOUND_SEQUENCE_VALIDATE` | 1 | Gateway 跑 Loop 前校验 messages 序列 |
| `BUTLER_GATEWAY_SESSION_INITIALIZING` | 1 | 首条会话冷启动期间入站入队不丢 |
| `BUTLER_WORKFLOW_QA_REPLAN` | 1 | `dev-qa-loop` / `ui-dev-qa-loop` QA 行首 FAIL 时重跑 implement |
| `BUTLER_WORKFLOW_QA_REPLAN_MAX` | 1 | QA FAIL replan 最多重跑 implement 次数 |
| `BUTLER_INLINE_TOOL_COMPRESS` | 0 | 实验：截断较早 tool 消息内容 |
| `BUTLER_THINKING_PROTOCOL` | 0 | `1` 时为 supports_thinking 模型追加 system 协议 hint |
| `BUTLER_REFLEXION_WRITE_EXPERIENCE` | 0 | `1` 时 Reflexion 写入 `.butler/experiences/reflexion.jsonl` |
| `BUTLER_INJECTION_SCORE` | 0 | `1` 时入站规则 injection 分写入 transcript |
| `BUTLER_INJECTION_LLM_SCORE` | 0 | `1` 时辅助模型对入站打 0–100 分（`BUTLER_INJECTION_LLM_BLOCK` 默认 85 阻断） |
| `BUTLER_INJECTION_LLM_BLOCK` | 85 | 与 `BUTLER_INJECTION_LLM_SCORE` 联用，≥ 阈值则阻断或门控 |
| `BUTLER_INJECTION_LLM_GATE` | 0 | `1` 且开启 LLM 评分时，高分走微信「确认」门控而非硬拒（需重发消息） |
| `BUTLER_INSTALL_PRE_SCAN` | 1 | MCP/Skill 安装前规则扫描（`butler mcp scan` / `skill install`） |
| `BUTLER_INSTALL_PRE_SCAN_FAIL_CLOSED` | 1 | 扫描 `block` 时拒绝安装 |
| `BUTLER_POST_SESSION_LAYERED` | 0 | `1` 时 post_session 抽取 persona/preference/experience 写入 `session_summary.json` |
| `BUTLER_TOOLS_ENGINE` | 1 | `0` 关闭 FC 能力检查；`BUTLER_TOOLS_ENGINE_FORCE_OFF=1` 强制无 tools |
| `BUTLER_TOOLS_ENGINE_SSOT` | 0 | `1` 时仅保留 effective mcp.yaml 中 server 的 `mcp_*` 工具 |
| `BUTLER_PROMPT_EVAL_LLM` | 0 | `1` 时 `butler prompt eval --llm` 对 pattern 通过项做辅助模型打分 |
| `BUTLER_PROMPT_EVAL_LLM_MIN` | 70 | LLM rubric 最低分（0–100） |
| `BUTLER_PROMPT_EVAL_LIVE_MAX` | 12 | `prompt eval --corpus-live-full` 单轮 case 上限 |
| `BUTLER_THINKING_BETA_HEADER` | （空） | 覆盖 anthropic-beta 头（需 `BUTLER_THINKING_PROTOCOL=1`） |
| `BUTLER_THINKING_BETA_MATRIX` | （空） | JSON 矩阵 `[{provider,model_contains,anthropic_beta}]` |
| `BUTLER_HUB_MANIFEST_CHECK` | 1 | `butler registry verify` 校验 bundled catalog + 远程 Hub |
| `BUTLER_OUTPUT_SCHEMA_REPAIR_MAX` | 2 | 终局 schema LLM 修复最多轮次 |
| `BUTLER_MEMORY_OBSERVER_QUEUE` | 0 | `1` 时 PostToolUse 写入 workspace `.butler/observations.db`（SQLite observation store） |
| `BUTLER_MEMORY_OBSERVATION_TTL_DAYS` | 0 | observation store 按天裁剪旧记录（0=关闭） |
| `BUTLER_MEMORY_OBSERVATION_MAX_ROWS` | 0 | observation store 行数上限（0=关闭） |
| `BUTLER_MEMORY_PREREAD` | 1 | `read_file` 前注入路径历史摘要 |
| `BUTLER_SESSION_SUMMARY` | 1 | SessionEnd 写 `.butler/session_summary.json` |
| `BUTLER_SESSIONS_LIST_LIMIT` | 20 | 微信 `/会话` 默认条数 |
| `BUTLER_STREAM_PROBE` | 0 | `1` 时 `/诊断` 触发最小 complete 探活 |
| `BUTLER_USAGE_PERSIST` | 1 | 用量写入 `~/.butler/usage/YYYY-MM-DD.jsonl` |
| `BUTLER_REFLEXION_EPHEMERAL` | 0 | `1` 时同工具连续失败注入 ephemeral 反思 |
| `BUTLER_ADVERSARIAL_MARK` | 1 | 入站消息含 injection 模式时前缀系统提示 |
| `BUTLER_PREFETCH_INJECTION_FILTER` | 1 | 记忆预取行过滤 injection 模式 |
| `BUTLER_PROVIDER_CIRCUIT` | 1 | 供应商熔断（见 `provider_health.py`） |
| `BUTLER_PROVIDER_FAILOVER` | （空） | 全局 failover 列表，逗号分隔 `provider/model` |
| `BUTLER_PROVIDER_CIRCUIT_FAILURES` | 3 | 熔断触发失败次数 |
| `BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS` | 60 | 熔断打开持续秒数 |
| `BUTLER_TOOL_LOOP_DETECTORS` | ping_pong,poll,circuit | 工具环检测（`off` 关闭） |
| `BUTLER_TOOL_LOOP_CIRCUIT_LIMIT` | 40 | 单轮工具调用熔断上限 |
| `BUTLER_TERMINAL_REQUIRE_APPROVAL` | 0 | `1` 时 terminal 须 Owner `/批准执行` |
| `BUTLER_OUTBOUND_BLOCK_DELAY_MS` | 0 | 微信多分块出站随机间隔（未设则用 `WECHAT_SEND_CHUNK_DELAY_SECONDS`） |
| `BUTLER_TRANSCRIPT_INDEX_MIN_BYTES` | 262144 | transcript 大于此值启用尾索引 |
| `BUTLER_HOOK_FAIL_CLOSED` | 0 | `1` 时 PreToolUse 非 0 退出即阻断工具 |

> OpenCode 对标运维速查：[`guides/opencode-parity.md`](../guides/opencode-parity.md)  
> OpenClaw 对标详表：[`plans/openclaw-learning-plan-2026-05.md`](../plans/comparisons/openclaw-learning-plan-2026-05.md)

## 安装与依赖分层

| 安装 | 用途 |
|------|------|
| `pip install -e .` | core 默认最小依赖（Loop / Transport / 配置 / SQLite 派生索引） |
| `pip install -e ".[wechat]"` | 微信 iLink 网关 |
| `pip install -e ".[mcp]"` | 薄 MCP client |
| `pip install -e ".[voice]"` | 语音/STT/TTS 能力 |
| `pip install -e ".[wechat-ocr]"` | OCR / 图片辅助 |
| `pip install -e ".[cli]"` | CLI 菜单增强 |
| `pip install -e ".[dev]"` | 开发 / 测试 / lint 依赖 |
| `pip install -e ".[pty]"` | PTY 兼容层 |
| `pip install -e ".[all]"` | 便捷安装集合（含 `wechat` / `wechat-ocr` / `cli` / `dev` / `voice` / `pty`，**不含** `mcp` 及以下五项） |
| `pip install -e ".[embeddings]"` | 本地 ONNX 语义嵌入（fastembed，替代 hashing / API） |
| `pip install -e ".[documents]"` | 文档转 Markdown（markitdown：PDF/Word/Excel/PPT） |
| `pip install -e ".[web]"` | 网页正文智能提取（trafilatura，替代正则） |
| `pip install -e ".[notify]"` | 多渠道通知（apprise：Telegram/Email/Slack 等 130+） |
| `pip install -e ".[analytics]"` | 本地数据查询（duckdb：CSV/JSON/Parquet/SQLite） |
| `pip install -e ".[vectors]"` | 向量检索（chromadb：嵌入式持久化，替代内存暴力搜） |

**原则**：新增外部依赖优先进入 `pyproject.toml` `optional-dependencies`；只有主循环、transport、配置和本地状态主路径必需的能力才进入 core 默认依赖。

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
| `BUTLER_GATEWAY_DURABLE_OUTBOX` | 1 | completion push 发送前写 `~/.butler/gateway_outbox/{pending,sent,failed}` |
| `BUTLER_GATEWAY_DURABLE_OUTBOX_MAX` | 200 | durable outbox 每状态最多保留条数 |
| `BUTLER_GATEWAY_QUEUE_PERSIST` | 0 | 入站队列 JSONL 持久化（`~/.butler/gateway/queue/`），启动时恢复 |
| `BUTLER_REMINDER_POLL_SECONDS` | 60 | 提醒轮询间隔（秒） |
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
| `BUTLER_WECHAT_INBOUND_MEDIA` | 0 | 微信入站媒体（图片/语音）处理 |
| `BUTLER_WECHAT_MEDIA_MAX_CHARS` | 4000 | 媒体 OCR/转写最大字符 |
| `BUTLER_WECHAT_STT_PROVIDER` | — | 语音转文字提供者 |
| `BUTLER_WECHAT_WHISPER_MODEL` | — | Whisper 模型名 |
| `BUTLER_WECHAT_VISION_FALLBACK` | 0 | 图片识别降级开关 |
| `BUTLER_WECHAT_VISION_TIMEOUT` | 30 | 图片识别超时（秒） |
| `BUTLER_WECHAT_PREFER_ILINK_TEXT` | 1 | 优先 iLink 文本消息 |
| `BUTLER_WECHAT_MINIMAX_API_HOST` | — | MiniMax API host 覆盖 |
| `BUTLER_GATEWAY_HUMAN_GATE_TTL` | 3600 | workflow 人工 gate 最短 60s 过期 |
| `BUTLER_DELEGATE_MAX_ITERATIONS` | 24 | 委派子 loop 默认迭代上限 |
| `BUTLER_CATALOG_INTEGRITY` | 1 | bundled catalog SHA-256 校验 |
| `BUTLER_TERMINAL_DANGER_CHECK` | 1 | terminal 危险命令模式阻断 |
| `BUTLER_TOOL_SELECTOR` | 1 | 工具数超阈值时按上下文缩小 schema |
| `BUTLER_TOOL_RESULT_CACHE` | 1 | 只读工具结果会话内短 TTL 缓存 |
| `BUTLER_COMPACTION_USE_HERMES_TEMPLATE` | 0 | 压缩摘要使用 Hermes v2 节结构 |
| `BUTLER_GATEWAY_PROGRESSIVE_STREAM` | 0 | 长流式任务渐进式微信补充消息 |
| `BUTLER_GATEWAY_TASK_MILESTONE` | 0 | 长轮次结构化进度消息（Antigravity 子集） |
| `BUTLER_GATEWAY_TASK_MILESTONE_SECONDS` | 90 | 里程碑最短等待秒数（通常需已发 progress ack） |
| `BUTLER_READ_FILE_SUMMARY_THRESHOLD` | 400 | 超大文件首次 read 返回行数摘要而非全文 |
| `BUTLER_MODE_CLASSIFIER` | 1 | 启发式 plan/do ephemeral 建议（不自动改模式） |
| `BUTLER_MODE_CLASSIFIER_AUX` | 0 | 边界句用 auxiliary 做 plan/do JSON 分类 |
| `BUTLER_MODE_CLASSIFIER_AUTO_PLAN` | 0 | 高置信 plan 句自动 `set_plan_mode`（微信慎用） |
| `BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION` | 0 | 委派子 Agent 每轮单工具（关并行） |
| `BUTLER_COMPACTION_PREFLIGHT_CHECKLIST` | 1 | 压缩摘要附带完成前自检要点 |
| `BUTLER_GATEWAY_EXTERNAL_ID_DEDUPE` | 1 | 微信 `external_id` 入站幂等（防重投双跑 Loop） |
| `BUTLER_TASK_STALE_MINUTES` | 60 | `running` 委派超过此时长标 stale |
| `BUTLER_TASK_STALE_AUTO_FAIL` | 0 | 是否自动将 stale 任务标为 failed |
| `BUTLER_TOOL_MASK_ENABLED` | 1 | 统一 tool output masking（Gemini 子集） |
| `BUTLER_TOOL_MASK_PROTECT_TOKENS` | 50000 | masking 保护最近 tool token 预算 |
| `BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET` | 50000 | 压缩摘要前 tool 消息 token 硬截断 |
| `BUTLER_IO_GUARDRAIL` | 1 | 入站明文密钥/过长消息检测 |
| `BUTLER_IO_GUARDRAIL_BLOCK` | 0 | 检测到 tripwire 时是否拦截（否则仅记录） |
| `BUTLER_IO_GUARDRAIL_PII` | 0 | 是否检测手机号/身份证模式 |
| `BUTLER_IO_GUARDRAIL_MAX_CHARS` | 0 | 入站最大字符（0=不限制） |
| `BUTLER_MCP_PROFILES` | 1 | MCP server 按 profile 过滤（`mcp.yaml` `profiles`） |
| `BUTLER_CORRECTIVE_RECALL` | 1 | 委派子 loop 工具失败时追加纠错检索块 |
| `BUTLER_CORPUS_ROUTING` | 1 | `search_project_knowledge` 多 scope 路由 |
| `BUTLER_ENABLE_DOWNLOAD` | 0 | 启用文件下载工具 |
| `BUTLER_DOWNLOAD_MAX_BYTES` | 10485760 | 下载文件大小上限 |
| `BUTLER_DOWNLOAD_ALLOW_HOSTS` | — | 下载白名单 host |
| `BUTLER_DATA_QUERY` | 0 | 启用 `data_query` 工具（duckdb） |
| `BUTLER_ENABLE_WEB_FETCH` | 0 | 启用薄 `web_fetch`（公网 URL，SSRF 校验） |
| `BUTLER_WEB_FETCH_MAX_BYTES` | 65536 | web_fetch 响应字节上限 |
| `BUTLER_WEB_FETCH_TIMEOUT` | 20 | web_fetch 超时（秒） |
| `BUTLER_DELEGATE_CONCURRENCY_LIMIT` | 1 | 同会话并发委派槽位限制 |
| `BUTLER_DELEGATE_MAX_CONCURRENT` | 2 | 每会话最大并行委派数 |
| `BUTLER_MID_TURN_COMPACT` | 1 | turn 内多轮 tool 后 mid-turn 压缩相位 |
| `BUTLER_EXECPOLICY` | 1 | YAML prefix_rule 终端策略（`~/.butler/execpolicy.yaml`） |
| `BUTLER_AUTO_REVIEW` | 0 | Guardian 子集：低风险只读 terminal 自动批准 |
| `BUTLER_AUTO_REVIEW_MAX_DENIALS` | 3 | 每 turn auto_review 连续拒绝上限 |
| `BUTLER_COMPACTION_INBOUND_BRIDGE` | 1 | 压缩迭代后注入紧急入站与 pending steer |
| `BUTLER_MCP_APPROVAL` | 1 | 变更类 MCP 工具需会话批准 |
| `BUTLER_GOAL_TOKEN_BUDGET` | 0 | `/循环` 累计 token 上限（0=不限制） |
| `BUTLER_REMOTE_COMPACT` | 0 | 对 OpenAI 兼容 host 尝试 `POST /v1/responses/compact`，失败回退 auxiliary |
| `BUTLER_REMOTE_COMPACT_URL` | — | 覆盖 compact 完整 URL |
| `BUTLER_REMOTE_COMPACT_FORCE` | 0 | 非 openai.com host 也尝试 remote compact |
| `BUTLER_TRANSCRIPT_MEMORY` | 0 | 启用 `/记忆提炼` 从 transcript JSONL 跑 PostSession 记忆通道 |
| `BUTLER_TRANSCRIPT_MEMORY_MAX_LINES` | 400 | 记忆提炼读取 transcript 尾部行数 |
| `BUTLER_EXECUTE_CODE` | 0 | 启用 `execute_code` 沙箱工具（须安全评审） |
| `BUTLER_SECRETS_FILE` | 1 | 从 `~/.butler/secrets.yaml` 加载 provider API key |
| `BUTLER_TERMINAL_SMART_APPROVE` | 1 | `/批准模式 <pattern>` 本会话放行危险 terminal |
| `BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST` | — | 向后剪枝最少回收字符数 |
| `BUTLER_BOT_LOOP_WHITELIST` | — | 逗号分隔 chat_id 白名单 |
| `BUTLER_TURN_TOKEN_BUDGET` | 1 | 句末 `+500k` / `/budget` 提高迭代上限 |
| `BUTLER_TURN_BUDGET_DEFAULT` | 200000 | 默认轮预算 token 数 |
| `BUTLER_TURN_BUDGET_MAX_ITERATIONS` | 50 | 轮预算最大迭代次数 |
| `BUTLER_TERMINAL_PIPE` | 0 | `1` 允许 terminal 工具有限管道（`\|`），仅白名单命令间可管道，最多 5 段 |
| `BUTLER_ONBOARDING_WELCOME` | 0 | `1` 新会话首条消息前附加 Butler 能力概览欢迎语 |
| `BUTLER_WORKFLOW_AUTO_RESUME` | 0 | `1` workflow 步骤确认后自动续跑（无需再发 `/workflow`） |
| `BUTLER_SKILL_SEMANTIC_ROUTING` | 1 | `1` Skill 路由使用 embedding 语义匹配（需非 hashing embedder） |
| `BUTLER_TOOL_SEMANTIC_SELECT` | 1 | `1` 工具选择加入 embedding 语义评分 |
| `BUTLER_MCP_SELF_SERVICE` | 1 | `1` 注册 `mcp_catalog_search`/`mcp_install`/`mcp_remove` Agent 工具 |
| `BUTLER_FACT_EXTRACTION` | 1 | `1` 压缩前从对话提取结构化事实，压缩后重注入 |

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
| `BUTLER_RUN_REAL_API_SMOKE` | 0 | `1` 跑真实 API 冒烟测试 |
| `BUTLER_SMOKE_DEEPSEEK_MODEL` | — | 冒烟用 DeepSeek 模型 |
| `BUTLER_SMOKE_DEEPSEEK_REASONER_MODEL` | — | 冒烟用 DeepSeek 推理模型 |
| `BUTLER_SMOKE_MINIMAX_MODEL` | — | 冒烟用 MiniMax 模型 |
| `BUTLER_SMOKE_QWEN_MODEL` | — | 冒烟用 Qwen 模型 |
| `BUTLER_NOTIFY_URLS` | — | 多渠道通知 URL（apprise 格式，CSV） |
| `BUTLER_PERMISSIONS_PARAM_BLACKLIST` | — | 权限参数黑名单 |
| `BUTLER_EXPERIENCE_PRUNE_DAYS` | 90 | 经验数据过期天数 |

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
- [`../plans/consolidation-2026-05.md`](../plans/archive/consolidation-2026-05.md)
