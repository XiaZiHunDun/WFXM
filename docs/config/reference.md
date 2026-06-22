# Butler 配置参考（env + YAML）

> **原则**：`.env` 仅放**密钥与部署覆盖**；稳定行为默认值优先写入 `~/.butler/config.yaml`（见 [`config.yaml.example`](config.yaml.example)）。  
> 完整密钥示例：仓库根 `.env.example`。  
> **代码默认 SSOT（Phase A1+）**：`butler/defaults/env_defaults.py` — 本表「默认」列须与其一致；见 [`env-config-maintainability-2026-06.md`](../plans/active/env-config-maintainability-2026-06.md)。  
> **配置放哪**：env / secrets / yaml / 运行时白名单 四分法见 [`config-surfaces.md`](config-surfaces.md)。  
> **按域查模块**：见 [`env-domains.md`](env-domains.md)。  
> **部署安全**：[`security.md`](security.md)（`BUTLER_ENV=prod` 等）。

## 优先级（effective 合并顺序）

| 层级 | 来源 | 说明 |
|------|------|------|
| 1 | 进程已设 `os.environ` | systemd `Environment=`、shell `export`、微信 `/config set`（当前进程） |
| 2 | 仓库根 `.env` | `init_dotenv()` 加载；**不覆盖**已设 env（`override=False`） |
| 3 | `~/.butler/config.yaml` | 结构化段；部分键可被 env **覆盖**（见各段说明） |
| 4 | `butler/defaults/env_defaults.py` | 代码默认 SSOT |

**env 覆盖 yaml 示例**：`BUTLER_WECHAT_MEDIA_MAX_CHARS` > `gateway.inbound_media.max_chars`；`BUTLER_GATEWAY_QUEUE_*` > `gateway.queue.*`；`BUTLER_MEMORY_*` / `BUTLER_SEMANTIC_*` > `memory.*`。详见 [`config-surfaces.md`](config-surfaces.md) §3.3。

无效数值 env（如 `BUTLER_FOO=abc`）由 `butler/env_parse.int_env` / `float_env` 回退默认并 `warning`，避免进程启动崩溃。

## 推荐：配置面（摘要）

完整四分法、合并顺序与白名单见 **[`config-surfaces.md`](config-surfaces.md)**。

| 放 `~/.butler/config.yaml` | 放 `.env` / `secrets.yaml` |
|---------------------------|---------------------------|
| `default_provider`、`butler_name`、`owner_name` | `MINIMAX_API_KEY` 等（`.env` 或 `secrets.yaml`） |
| `models.*`、`auxiliary.*`、`embedding.*`、`llm_fallback.*` | `WECHAT_TOKEN`、`WECHAT_ACCOUNT_ID` |
| `gateway.inbound_media` | `BUTLER_OWNER_WECHAT_ID`、`BUTLER_PROJECTS_DIR` 等部署项 |
| — | 多数 `BUTLER_*` 开关（默认见 `env_defaults.py`） |

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
| `BUTLER_GATEWAY_SUPPRESS_COMPLETION_AFTER_MAIN` | 1 | 主回复已发则抑制委派/整轮/工作流完成推送（防刷屏） |
| `BUTLER_GATEWAY_MAX_SUPPLEMENTARY_PER_TURN` | 2 | 每轮最多额外微信条数（完成推送、队列 drain、里程碑等） |
| `BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY` | 1 | 工作流完成推送 |
| `BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS` | 90 | 完成推送最短等待时间（≥ progress ack 间隔） |
| `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` | 3 | `DELEGATE_COMPLETION_MODE=each` 时每轮最多推送次数 |

## 项目与工具安全

| 变量 | 说明 |
|------|------|
| `BUTLER_PROJECTS_DIR` | 项目根（默认仓库 `projects/`） |
| `BUTLER_TOOL_SAFE_ROOT` | 工具路径沙箱根 |
| `BUTLER_LEAD_PROJECTS` | 厂长模式项目列表（逗号分隔；可被 `project.yaml` `lead: true` 补充） |
| `BUTLER_HOME` | `~/.butler` | Butler 数据根目录 |
| `BUTLER_DATA_HOME` | `~/.butler` | 网关单例锁目录（`gateway.singleton.lock`；默认同 `BUTLER_HOME`） |
| `BUTLER_TENANT` | default | 多租户隔离键；日常工具数据存于 `~/.butler/tenants/<tenant>/` |
| `BUTLER_PROJECT_ROOT` | — | 记忆层项目根覆盖（默认当前项目 workspace） |
| `BUTLER_SECRETS_PATH` | — | 凭证文件路径覆盖（默认 `~/.butler/secrets.yaml`） |
| `BUTLER_GOAL_LOOP` | 0 | `1` 启用 `/循环` 目标循环模式 |
| `BUTLER_DISABLE_COMPACT` | 0 | `1` 禁用所有压缩（与 `BUTLER_DISABLE_AUTO_COMPACT` 并存） |
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
| `BUTLER_RUNTIME_PUSH_DRAIN_COOLDOWN_SECONDS` | 300 | iLink 限流后跳过 `drain-push` 的冷却秒数（避免反复 hammer） |
| `BUTLER_RUNTIME_FAIL_ALERT_STREAK` | 3 | 连续失败告警 |
| `BUTLER_RUNTIME_SMOKE_PUSH` | 0 | 冒烟是否真推送 |
| `BUTLER_RUNTIME_PUSH_QUEUE` | 1 | 推送入队开关 |

## 记忆

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_SEMANTIC_MEMORY` | 0 | 启用本地向量；`config.yaml` `memory.semantic_enabled` ← env 覆盖 |
| `BUTLER_SEMANTIC_SEARCH_LIMIT` | 8 | 单次语义搜索返回条数；yaml `memory.search_limit` ← env 覆盖 |
| `BUTLER_SYNC_CONVERSATION_MEMORY` | 0 | 不把每轮聊天写入 experience |
| `BUTLER_QUEUE_PREFETCH` | 1 | 推荐：下轮预取缓存 |
| `BUTLER_PREFETCH_CACHE_TTL` | 120 | 预取缓存 TTL（秒） |
| `BUTLER_PREFETCH_MAX_CHARS` | 4000 | 单层预取字符上限 |
| `BUTLER_PREFETCH_TOTAL_MAX_CHARS` | 12000 | 全部预取合计字符上限 |
| `BUTLER_PREFETCH_PROJECT_HITS` | 5 | 项目层预取条数 |
| `BUTLER_PREFETCH_PROJECT_MAX_CHARS` | 3000 | 项目层预取字符上限 |
| `BUTLER_PREFETCH_EXPERIENCE_HITS` | 5 | 经验层预取条数 |
| `BUTLER_PREFETCH_FACTS_MAX_CHARS` | 2000 | 事实预取字符上限 |
| `BUTLER_MEMORY_RECALL_LAYERS` | 1 | 分层召回 index/fetch/timeline；yaml `memory.recall_layers_enabled` ← env 覆盖 |
| `BUTLER_MEMORY_ACCESS_BOOST` | 0.12 | 记忆访问频率权重加成；yaml `memory.ranking.access_boost` |
| `BUTLER_MEMORY_HALF_LIFE_DAYS` | 30 | 记忆衰减半衰期（天）；yaml `memory.ranking.half_life_days` |
| `BUTLER_MEMORY_PRIVATE_TAGS` | — | 逗号分隔私有标签 |
| `BUTLER_MEMO_ENABLED` | 1 | 0=关闭备忘录模块（memo_add/list/search/update/delete 工具） |
| `BUTLER_CONTACTS_ENABLED` | 1 | 0=关闭通讯录模块（contact_add/find/update/delete/list 工具） |
| `BUTLER_EXPENSE_ENABLED` | 1 | 0=关闭记账模块（expense_add/summary/list/delete 工具） |
| `BUTLER_HABITS_ENABLED` | 1 | 0=关闭习惯打卡模块（habit_create/checkin/stats/list/delete 工具） |
| `BUTLER_FTS_HYBRID_WEIGHT` | 0.3 | 全文/向量混合检索权重 |
| `BUTLER_VECTOR_HYBRID_WEIGHT` | 0.5 | 向量检索在混合中的权重；yaml `memory.hybrid.vector_weight` |
| `BUTLER_EMBEDDING_PROVIDER` | local | 嵌入提供者：local/fastembed/openai/minimax。**生产推荐** `fastembed`（`bash scripts/butler-observability-provision.sh` 一键配置）。**env 覆盖** `~/.butler/config.yaml` → `embedding.*` |
| `BUTLER_EMBEDDING_MODEL` | hashing-v1 | 嵌入模型名。fastembed 推荐 `BAAI/bge-small-en-v1.5` |

**`config.yaml` 模型正交段**（见 [`config.yaml.example`](config.yaml.example) · [`layered-model-config.md`](../architecture/layered-model-config.md)）：

| 段 | 键 | 说明 |
|----|-----|------|
| `embedding` | `provider`, `model` | 向量嵌入；env `BUTLER_EMBEDDING_*` 优先 |
| `llm_fallback` | `enabled`, `chain` | 主 LLM 失败降级：`auto`（minimax 时追加有 key 的 deepseek/qwen/openai）、`[]` 或显式列表 |
| `remote_compact` | `model` | OpenAI 风格 `/responses/compact`；空则跟 `auxiliary.compression.model` |

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
| `BUTLER_INGEST_ENABLED` | 0 | EXT-3：`butler memory ingest` 将 PDF/Office 转为 `.butler/ingest/*.md` |
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
| `BUTLER_TOOL_PRUNE_DEFAULT_CHARS` | 800 | 默认工具输出剪枝字符 |
| `BUTLER_TOOL_PRUNE_PRESERVE_CHARS` | 2400 | 剪枝保护字符 |
| `BUTLER_TOOL_PRUNE_KEEP_RECENT` | 4 | 保留最近 N 个工具输出不剪枝 |
| `BUTLER_TOOL_PRUNE_CLEARABLE_CHARS` | 400 | 可完全清除的工具输出阈值 |
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
| `BUTLER_MCP_STDIO_ALLOW_COMMANDS` | python,python3,uvx | stdio 可执行命令白名单；**EXT-1 Firecrawl** 须加 `npx` |
| `BUTLER_MCP_HTTP_HOSTS_ALLOW` | 空 | **HTTP transport** MCP server 额外允许的 Host；纯 stdio MCP 可留空 |
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
| `BUTLER_SKILL_AUTO_SYNC_PROJECT` | 1 | registry `install`/`upgrade` 后自动 `skills sync --project`（目标为 `BUTLER_DEFAULT_PROJECT` 且含 `stack.yaml`） |
| `BUTLER_DEPLOY_PROFILE` | （空） | pip 剖面：`gateway` / `dev` / `all`；与 `stack.yaml` `deploy_profile` 对照 |
| `BUTLER_MCP_CATALOG` | 1 | MCP 目录 `butler mcp add` |
| `BUTLER_MCP_CATALOG_URLS` | 空 | 远程 MCP catalog JSON/YAML URL（CSV，SSRF 校验；与内置 catalog 合并，同名以内置为准） |
| （CLI） | — | `butler mcp add <id> --workspace <dir>` 写入项目 `.butler/mcp.yaml`；`--global` 强制全局；probe 失败不写 yaml |
| `BUTLER_MCP_AUTO_PROJECT_TOOLS` | 1 | 项目层 MCP 安装后自动向 `project.yaml` tools 追加 `mcp_*`（仅当 tools 非空且尚无 mcp 项） |
| `GITHUB_TOKEN` | — | GitHub API（技能拉取） |
| `BUTLER_SESSION_TRANSCRIPT` | 1 | `~/.butler/sessions/<key>/transcript.jsonl`；含 compact / `bot_loop_suppressed` 等事件 |
| `BUTLER_SESSION_TRANSCRIPT_MAX_BYTES` | 52428800 | transcript 轮转阈值 |
| `BUTLER_REASONING_TRACE` | 1 | `0` 关闭 transcript `reasoning_step` / `reflect_step` 与 `/诊断` 推理摘要行 |
| `BUTLER_REASONING_DIAG_SCAN_LINES` | 2000 | `/诊断` 扫描最近 N 行 transcript 取最近推理/反思（避免 tail=80 被淹没） |
| `BUTLER_PLAN_REASON_GRAPH` | 1 | `0` 关闭规划模式 DoT-lite 图（`~/.butler/sessions/<key>/reason_graph.json`） |
| `BUTLER_SESSION_HYDRATE` | 1 | 新建 Loop 时从 transcript 注入 read_file 事实块 |
| `BUTLER_SESSION_TOOL_INDEX` | 1 | 从 transcript 解析本轮 `read_file` 路径索引 |
| `BUTLER_SESSION_RECOVERY_NOTICE` | 1 | 冷启动后首条回复附会话恢复提示 |
| `BUTLER_WORKSPACE_ANCHOR_STRICT` | 1 | 相对路径优先锚定当前项目 workspace |
| `BUTLER_TURN_SUMMARY_LINE` | 1 | `0` 关闭长回复前工具摘要行（`📎 读了N文件·…`） |
| `BUTLER_TURN_SUMMARY_MIN_CHARS` | 400 | 触发摘要的最小回复长度 |
| `BUTLER_MORNING_BRIEF` | 0 | `1` 时每日 timer 向 Owner 微信推送 `/简报` 内容 |
| `BUTLER_TOOL_AUDIT_PERSIST` | 1 | tool_audit 追加写入 `sessions/<key>/tool_audit.jsonl` |
| `BUTLER_READ_BEFORE_EDIT` | 1 | patch/write 前须 read_file + mtime |
| `BUTLER_READ_STATE_MAX_ENTRIES` | 100 | read state LRU 上限 |
| `BUTLER_DISABLE_AUTO_COMPACT` | 0 | `1` 关闭 LLM 摘要压缩 |
| `BUTLER_CONTEXT_OUTPUT_RESERVE` | 20000 | 压缩时为模型输出保留的 token 数（CC autoCompact 对齐）；yaml `context.budget.output_reserve` ← env 覆盖 |
| `BUTLER_CONTEXT_COMPACT_RESERVE` | 13000 | 自动压缩触发缓冲 token |
| `BUTLER_CONTEXT_WARNING_BUFFER` | 20000 | 上下文 warning 阈值缓冲 |
| `BUTLER_CONTEXT_ERROR_BUFFER` | 20000 | 上下文 error 阈值缓冲 |
| `BUTLER_CONTEXT_BLOCKING_BUFFER` | 3000 | 上下文阻塞阈值缓冲 |
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
| `BUTLER_INSTRUCTION_WALKUP_MAX_CHARS` | 4000 | read_file 后注入 AGENTS.md 最大字符 |
| `BUTLER_TOOL_IMPLICIT_CONTEXT` | 1 | `0` 关闭 dispatch 时注入 `_butler_*` 隐式参数 |
| `BUTLER_SCHEMA_OPTIMIZE` | 1 | LLM 调用前预净化 tool schema |
| `BUTLER_TOKEN_COST_ESTIMATE` | 0 | `1` 时 `/诊断` 显示粗算美元成本 |
| `BUTLER_COST_CALIBRATION_PERSIST` | 1 | `0` 关闭成本事件落盘（`~/.butler/metrics/cost_events_*.jsonl`） |
| `BUTLER_COST_CALIBRATION_DAYS` | 7 | `/成本` 与 `cost_calibration_cli report` 汇总天数 |
| `BUTLER_COST_USD_CNY_RATE` | 7.2 | 成本标定块人民币粗算汇率 |
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
| `BUTLER_MCP_DEFERRED_SAME_TURN` | 0 | `1` 时经验 `mcp:` promote 后同轮合并 schema 进 `turn_tools`（默认下一轮） |
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
| `BUTLER_POST_SESSION_LAYERED` | 0 | `1` 时 post_session 抽取 persona/preference/experience 写入 `session_summary.json`（默认 0，推荐按需设为 1） |
| `BUTLER_TOOLS_ENGINE` | 1 | `0` 关闭 FC 能力检查；`BUTLER_TOOLS_ENGINE_FORCE_OFF=1` 强制无 tools |
| `BUTLER_TOOLS_ENGINE_SSOT` | 0 | `1` 时仅保留 effective mcp.yaml 合并视图中 server 的 `mcp_*` 工具；effective 见 [`execution-surface-design.md`](../architecture/execution-surface-design.md) §4.6 |
| `BUTLER_PROMPT_EVAL_LLM` | 0 | `1` 时 `butler prompt eval --llm` 对 pattern 通过项做辅助模型打分 |
| `BUTLER_PROMPT_EVAL_LLM_MIN` | 70 | LLM rubric 最低分（0–100） |
| `BUTLER_PROMPT_EVAL_LIVE_MAX` | 12 | `prompt eval --corpus-live-full` 单轮 case 上限 |
| `BUTLER_THINKING_BETA_HEADER` | （空） | 覆盖 anthropic-beta 头（需 `BUTLER_THINKING_PROTOCOL=1`） |
| `BUTLER_THINKING_BETA_MATRIX` | （空） | JSON 矩阵 `[{provider,model_contains,anthropic_beta}]` |
| `BUTLER_HUB_MANIFEST_CHECK` | 1 | `butler registry verify` 校验 bundled catalog + 远程 Hub |
| `BUTLER_OUTPUT_SCHEMA_REPAIR_MAX` | 2 | 终局 schema LLM 修复最多轮次 |
| `BUTLER_MEMORY_OBSERVER_QUEUE` | 0 | `1` 时 PostToolUse 写入 workspace `.butler/observations.db`（SQLite observation store） |
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
| `BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS` | 120 | 熔断打开持续秒数 |
| `BUTLER_TOOL_LOOP_DETECTORS` | ping_pong,poll,circuit | 工具环检测（`off` 关闭） |
| `BUTLER_TOOL_LOOP_CIRCUIT_LIMIT` | 40 | 单轮工具调用熔断上限 |
| `BUTLER_TERMINAL_REQUIRE_APPROVAL` | 0 | `1` 时 terminal 须 Owner `/批准执行` |
| `BUTLER_OUTBOUND_BLOCK_DELAY_MS` | 0 | 微信多分块出站随机间隔（未设则用 `WECHAT_SEND_CHUNK_DELAY_SECONDS`） |
| `BUTLER_TRANSCRIPT_INDEX_MIN_BYTES` | 262144 | transcript 大于此值启用尾索引 |
| `BUTLER_HOOK_FAIL_CLOSED` | 0 | `1` 时 PreToolUse 非 0 退出即阻断工具 |

> **Hook 子进程运行时注入**（非用户配置）：`BUTLER_HOOK_EVENT` / `BUTLER_HOOK_INPUT` / `BUTLER_HOOK_TOOL` 由 `hooks/runner.py` 注入子进程，勿写入 `.env`。

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
| `pip install -e ".[all]"` | 便捷安装集合（含 `wechat` / `wechat-ocr` / `cli` / `dev` / `voice` / `pty` / `embeddings` / `vectors` / `observability` / `tokens`，**不含** `mcp` / `web` / `documents` / `notify` / `analytics`） |
| `pip install -e ".[gateway]"` | **微信 Gateway 生产推荐**：`wechat` + `mcp` + `embeddings` + `vectors` + `web`（`butler-gateway-ops.sh upgrade` 使用） |

**主机代理（非 `BUTLER_*`）**：Gateway `.env` 可设 `HTTP_PROXY` / `HTTPS_PROXY`（如 Mihomo `127.0.0.1:7890`），供 `web_search`、Skill Registry GitHub 拉取、httpx 外联；与 `BUTLER_WEB_SEARCH_TRY_DIRECT` 配合（有代理时默认不走直连）。
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
| `BUTLER_GATEWAY_QUEUE_MODE` | followup | 全局队列模式：followup / collect / interrupt / steer；`config.yaml` `gateway.queue.mode` 可被 env 覆盖；会话 `/queue` 可再覆盖 |
| `BUTLER_GATEWAY_QUEUE_CAP` | 20 | 每会话队列上限；yaml `gateway.queue.cap` ← env 覆盖 |
| `BUTLER_GATEWAY_QUEUE_DROP` | summarize | 溢出策略：summarize / old / new；yaml `gateway.queue.drop` ← env 覆盖 |
| `BUTLER_GATEWAY_QUEUE_COLLECT_DEBOUNCE_MS` | 500 | collect 模式 debounce；yaml `gateway.queue.collect_debounce_ms` ← env 覆盖 |
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
| `BUTLER_WECHAT_CONTENT_DEDUP_TTL` | 20 | 微信内容去重 TTL（秒） |
| `BUTLER_WECHAT_MESSAGE_ID_DEDUP_TTL` | 86400 | 微信消息 ID 去重 TTL（秒）；防 iLink 重复投递重放旧消息 |
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
| `BUTLER_DATA_QUERY` | 1 | 启用 `data_query` 工具（duckdb） |
| `BUTLER_ENABLE_WEB_FETCH` | 0 | 启用薄 `web_fetch`（公网 URL，SSRF 校验） |
| `BUTLER_ENABLE_WEB_SEARCH` | 0 | 启用 `web_search` 工具（DuckDuckGo） |
| `BUTLER_NETWORK_SEARCH_GATE` | 1 | 检索意图下须先 `web_search` 再 Firecrawl search |
| `BUTLER_FIRECRAWL_SEARCH_MAX_PER_TURN` | 3 | 每轮 `mcp_firecrawl_*_search` 上限 |
| `BUTLER_FIRECRAWL_AGENT_MAX_PER_TURN` | 0 | 每轮 `mcp_firecrawl_*_agent` 上限（0=检索场景禁用） |
| `BUTLER_FIRECRAWL_FEEDBACK_MAX_PER_TURN` | 0 | 每轮 `mcp_firecrawl_*_feedback` 上限（0=禁用） |
| `BUTLER_SESSION_RECOVERY_NOTICE` | 0 | 是否在回复前展示 transcript 恢复提示 |
| `BUTLER_WEB_SEARCH_TRY_DIRECT` | 0 | 有代理时是否仍尝试直连（默认否，省预算） |
| `BUTLER_WEB_SEARCH_EMPTY_MAX_PER_TURN` | 2 | 每轮空 `web_search` 上限（超出改 Firecrawl） |
| `BUTLER_WEB_SEARCH_RETRIES` | 2 | DuckDuckGo 多后端重试轮数 |
| `BUTLER_WEB_SEARCH_TIMEOUT` | 15 | 单次 HTTP 尝试超时（秒，上限 30） |
| `BUTLER_WEB_SEARCH_BUDGET` | 60 | 单次 `web_search` 总时间预算（秒，上限 300） |

**`web_search` 运维**：Gateway 内间歇零结果时运行 `bash scripts/butler-web-search-probe.sh`（与 systemd 同 `.env`）；有 `HTTP(S)_PROXY` 时默认只走代理（`BUTLER_WEB_SEARCH_TRY_DIRECT=1` 才试直连）。检索任务以 Firecrawl 兜底，勿重复空搜。详见 EXT-1 [`ext-1-web-scrape-mcp-2026-06.md`](../plans/active/extension-candidates/ext-1-web-scrape-mcp-2026-06.md)。

| `BUTLER_IMAGE_GENERATION` | 1 | 启用 `generate_image`（MiniMax image-01） |
| `BUTLER_TTS` | 1 | 启用 `synthesize_speech`（MiniMax TTS HD） |
| `BUTLER_WEB_FETCH_MAX_BYTES` | 65536 | web_fetch 响应字节上限 |
| `BUTLER_WEB_FETCH_TIMEOUT` | 20 | web_fetch 超时（秒） |
| `FIRECRAWL_API_KEY` | — | **EXT-1** Firecrawl MCP；推荐 `~/.butler/secrets.yaml`，勿提交 git |
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
| `BUTLER_EXECUTE_CODE_TIMEOUT` | 30 | 代码执行超时（秒） |
| `BUTLER_EXECUTE_CODE_ALLOW_NETWORK` | 0 | `1` 允许沙箱网络访问 |
| `BUTLER_SECRETS_FILE` | 1 | 从 `~/.butler/secrets.yaml` 加载 provider API key |
| `BUTLER_TERMINAL_SMART_APPROVE` | 1 | `/批准模式 <pattern>` 本会话放行危险 terminal |
| `BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST` | — | 向后剪枝最少回收字符数 |
| `BUTLER_BOT_LOOP_WHITELIST` | — | 逗号分隔 chat_id 白名单 |
| `BUTLER_TURN_TOKEN_BUDGET` | 1 | 句末 `+500k` / `/budget` 提高迭代上限 |
| `BUTLER_TURN_BUDGET_DEFAULT` | 500000 | 默认轮预算 token 数 |
| `BUTLER_TURN_BUDGET_MAX_ITERATIONS` | 60 | 轮预算最大迭代次数 |
| `BUTLER_TERMINAL_PIPE` | 0 | `1` 允许 terminal 工具有限管道（`\|`），仅白名单命令间可管道，最多 5 段 |
| `BUTLER_WORKFLOW_AUTO_RESUME` | 0 | `1` workflow 步骤确认后自动续跑（无需再发 `/workflow`） |
| `BUTLER_SKILL_INJECTION_MODE` | fallback | `fallback`：有经验命中则跳过未验证 Skill 全文；`ref_only`：仅经验 `skill:<名>` 指针；`always`：每轮 Router 注入（旧行为） |
| `BUTLER_SKILL_FALLBACK_MIN_EXPERIENCE_HITS` | 1 | `fallback`/`ref_only` 下视为「经验已覆盖」的最少命中条数 |
| `BUTLER_SKILL_SEMANTIC_ROUTING` | 1 | `1` Skill 路由使用 embedding 语义匹配（需非 hashing embedder） |
| `BUTLER_TOOL_SEMANTIC_SELECT` | 1 | `1` 工具选择加入 embedding 语义评分 |
| `BUTLER_MCP_SELF_SERVICE` | 1 | `1` 注册 `mcp_catalog_search`/`mcp_install`/`mcp_remove` Agent 工具 |
| `BUTLER_FACT_EXTRACTION` | 1 | `1` 压缩前从对话提取结构化事实，压缩后重注入 |

Shell Stop 钩子：`exit 2` 或 JSON `decision:block` → **循环内**注入 user 消息并续跑（`stop_hook_blocked`），非仅替换最终回复。

**P2 工作流权限**（`.butler/permissions.yaml`）：`workflow_steps.<step_id>.tools` 限制 DAG 节点内工具；`requires_approval: true` 的步骤需微信「确认」后再次 `/workflow <name>`。命令：`/确认`、`/取消`。DAG 节点上限 50，默认并行度 ≤ 5（`BUTLER_WORKFLOW_MAX_PARALLEL`）。

**Runtime 任务审批**：`runtime/jobs.yaml` 中 `mode: mutating` 的任务默认 `approval.required: true`，须 Owner `/批准运行 <job_id>` 后方可执行，有效期 `approval.expires_hours`（默认 48h）。`approval.required: false` 为高级旁路配置，仅适用于低风险改盘任务——**设置前须确认任务无破坏性**。

项目权限：`.butler/permissions.yaml` 或 `project.yaml` 的 `permissions.rules`（`allow`/`deny`/`ask`，**后写规则覆盖前写**，无 LLM classifier）。`external_directory` 节控制工作区外路径；Owner 微信 **`/批准一次`**、**`/始终允许 <权限>`**、**`/权限`** 写入 `~/.butler/sessions/<session_key>/approvals.json`。`delegate_subagent` 节控制委派子 loop 工具白名单；委派子 loop 使用 `child_session_key` 独立 transcript（`{session}::delegate::{task_id}`）。

运维与 H1–H10 见 [`guides/wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md)。

## 冒烟 / 开发

| 变量 | 说明 |
|------|------|
| `BUTLER_WECHAT_DEV_SMOKE` | `/诊断` 显示开发项 |
| `BUTLER_CLI_STREAM_MODE` | CLI 流式 `live` / `off` |
| `BUTLER_RUN_REAL_API_SMOKE` | 0 | `1` 跑真实 API 冒烟测试 |
| `BUTLER_PERMISSIONS_PARAM_BLACKLIST` | — | 权限参数黑名单 |
| `BUTLER_EXPERIENCE_PRUNE_DAYS` | 90 | **仅** `category=conversation` 会话回声硬删除（天）；`0`=关闭；**不**删 ops/note 长期经验 — 见 [`memory-ops.md`](../guides/memory-ops.md) §记忆卫生 |

### 脚本 / 测试专用（`butler/` 无 reader）

由 `scripts/*.sh` 或 `tests/` 读取，**非**运行时模块配置：

| 变量 | 说明 |
|------|------|
| `BUTLER_RUNTIME_RUN_CONSISTENCY` | `1` 时 `butler-runtime-smoke.sh` 跑 consistency-weekly |
| `BUTLER_RUNTIME_SMOKE_PUSH` | `1` 时 runtime 冒烟允许真推送（默认 0） |
| `BUTLER_SMOKE_DEEPSEEK_MODEL` | `tests/test_real_api_smoke.py` 用 DeepSeek 模型 |
| `BUTLER_SMOKE_DEEPSEEK_REASONER_MODEL` | 同上，推理模型 |
| `BUTLER_SMOKE_MINIMAX_MODEL` | 冒烟用 MiniMax 模型 |
| `BUTLER_SMOKE_QWEN_MODEL` | 冒烟用 Qwen 模型 |
| `BUTLER_DISABLE_EXPERIMENTAL_CACHE` | 仅测试：`test_sprint16_perf11_9_llm_retry_debug.py` |

> `BUTLER_NOTIFY_URLS`（apprise 多渠道）**尚未接入** `butler/` 运行时；勿在生产 `.env` 中依赖。

## 工具名别名（`project.yaml` / 提示词 → 注册表）

| 文档或 yaml 中写法 | 注册表 canonical |
|-------------------|------------------|
| `edit_file` | `patch` |
| `search_code` | `search_files` |
| `run_shell` | `terminal` |
| `skill_list` | `skills_list` |

Lead 厂长模式另禁 `patch` / `terminal` / `write_file`，保留 `delegate_task`、`read_file`、`run_workflow` 等 — 见 [`architecture/project-lead-decision.md`](../architecture/project-lead-decision.md)。

## Sprint 1-5 新增环境变量 (2026-05)

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_CONFIRM_WRITE_OPS` | `1` | 写操作 (write_file/patch_file) 二次确认开关 |
| `BUTLER_OBSERVATION_TTL_DAYS` | `90` | Observation Store 数据保留天数 |
| `BUTLER_ONBOARDING_WELCOME` | `1` | 首次会话欢迎消息（`0` 关闭） |

## Sprint 6+ 增量开关 (审计 5.1.10 同步)

> 本节为 `tests/test_butler_env_sync.py` 自动校验入口；新增 `BUTLER_` env
> 必须在 `.env.example` 与本节**同时**出现，否则 `pytest -k butler_env_sync` 失败。

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_RUNTIME_DIRS` | 见 `butler/config.py` | runtime 写入白名单目录（逗号分隔） |
| `BUTLER_TOOL_RETRY_MAX` | `2` | 单 tool 失败重试上限 |
| `BUTLER_TOOL_RETRY_BACKOFF_SECONDS` | `0.4` | 工具重试退避基数（秒） |
| `BUTLER_TOOL_PAIR_REPAIR` | `1` | 配对工具（read_file/write_file）错误时自动修复 |
| `BUTLER_TOOL_SELECTOR_THRESHOLD` | `12` | 工具数超过此值才启用 LLM 选择器 |
| `BUTLER_TOOL_CALL_LIMIT_EXEMPT` | — | 不受 `PerToolCallLimiter` 约束的 tool 名（逗号分隔） |
| `BUTLER_TOOL_NAMES` | — | 自定义已知 tool 名白名单（normalize 用，逗号分隔） |
| `BUTLER_TOOL_MASK_MIN_PRUNABLE` | `30000` | tool 输出掩码：可脱敏最小字符 |
| `BUTLER_TOOL_RESULT_CACHE_TTL` | `120` | 工具结果缓存 TTL（秒） |
| `BUTLER_HASHLINE_READ` | `0` | `1` = read_file 返回 hashline 锚点 |
| `BUTLER_HASHLINE_PATCH` | `1` | `1` = patch 工具支持 hashline 定位 |
| `BUTLER_INLINE_TOOL_COMPRESS_MAX_CHARS` | `1200` | 单 tool 输出超过此值触发内联压缩 |
| `BUTLER_INLINE_TOOL_COMPRESS_KEEP` | `6` | 内联压缩后保留最近 N 行 |
| `BUTLER_TERMINAL_PATTERN_APPROVE_TTL` | `86400` | `/批准一次 pattern` 有效期（秒） |
| `BUTLER_REGISTRY_ALLOWED_HOSTS` | — | registry 拉取白名单 host（逗号分隔） |
| `BUTLER_MEMORY_MAX_LINES` | `200` | 单 markdown chunk 最大行数 |
| `BUTLER_MEMORY_MAX_BYTES` | `25600` | 单 markdown chunk 最大字节数 |
| `BUTLER_MODE_CLASSIFIER_MIN_CHARS` | `36` | 触发 mode classifier 的最小 query 字符数 |
| `BUTLER_INTENT_KEYWORDS` | — | 自定义 intent 关键词（追加默认，逗号分隔） |
| `BUTLER_INTENT_KEYWORDS_OFF` | `0` | `1` = 关闭 intent 关键词 |
| `BUTLER_INSTRUCTION_WALKUP_MAX_FILES` | `3` | read_file 触发 walkup 单轮最多文件数 |
| `BUTLER_GATEWAY_PROGRESSIVE_MIN_CHARS` | `240` | 渐进推送触发字符阈值 |
| `BUTLER_GATEWAY_PROGRESSIVE_INTERVAL` | `45` | 渐进推送最小间隔（秒） |
| `BUTLER_GATEWAY_PROGRESS_MAX_ACK_MESSAGES` | `1` | 单次进度确认最多消息数 |
| `BUTLER_GATEWAY_TYPING_REFRESH_SECONDS` | `4` | 输入提示刷新间隔（秒） |
| `BUTLER_GATEWAY_TYPING_FETCH_TIMEOUT_SECONDS` | `2` | 输入提示拉取超时（秒） |
| `BUTLER_GATEWAY_QUEUE_DRAIN_FOLLOWUP` | `1` | drain 队列中 followup 消息的并发上限 |
| `BUTLER_GATEWAY_DELEGATE_PUSH_ALWAYS` | `0` | `1` = 委派任务每次完成都推微信 |
| `BUTLER_OUTBOUND_PII_SCRUB_EMAIL` | `1` | 出站脱敏是否包含邮箱（`0` 关闭） |
| `BUTLER_RULES_ENGINE` | `1` | `0` = 关闭规则引擎 |
| `BUTLER_RULES_MAX_CHARS` | `6000` | 规则引擎单次输出最大字符 |
| `BUTLER_TODO_CONTINUATION` | `1` | `0` = 关闭 todo 持续推进 |
| `BUTLER_TODO_CONTINUATION_MAX` | `2` | todo 单轮最大续推次数 |
| `BUTLER_TODO_STAGNATION_MAX` | `2` | todo 停滞容忍次数 |
| `BUTLER_POST_SESSION_BUFFER_MESSAGES` | `8` | post-session 缓冲消息条数 |
| `BUTLER_TURN_BUDGET_MIN_ITERATIONS` | `30` | 单轮 tool 调用的最小迭代数 |
| `BUTLER_WECHAT_RATE_LIMIT_BACKOFF_MAX` | — | 微信限流退避上限（秒） |
| `BUTLER_CLI_SHOW_REASONING` | `0` | `1` = CLI 显示 reasoning |
| `BUTLER_CATALOG_INTEGRITY_FAIL_CLOSED` | `1` | `0` = catalog 校验失败仍尝试加载 |
| `BUTLER_EXTRA_TOOLS` | — | 项目维度默认启用的额外工具（逗号分隔） |
| `BUTLER_TRANSCRIPT_SEARCH_MAX_HITS` | `15` | transcript 搜索单次最多命中 |
| `BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS` | `5` | transcript 搜索最多扫描的会话数 |

### L4 开发引擎（Development Engine）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_DEV_ENGINE` | `1` | `0` = 关闭内置开发引擎；关闭后 dev 角色使用传统工作流 |
| `BUTLER_DEV_AUTO_VERIFY` | `1` | `0` = 关闭编辑后自动验证；手动调 `dev_verify` |
| `BUTLER_DEV_VERIFY_SUCCESS_GATE` | `1` | `1` = dev 委派有编辑但 verify 未绿时 `success=false`（`DEV_VERIFY_GATE`） |
| `BUTLER_DEV_VERIFY_TIMEOUT` | `300` | `dev_verify` 单个验证层级超时（秒） |
| `BUTLER_DEV_MAX_FIX_ROUNDS` | `3` | 同一类错误最大修复轮次，超限报 STUCK |
| `BUTLER_DEV_ROLLBACK_ENABLED` | `1` | `0` = 禁用 `dev_rollback` 工具 |
| `BUTLER_DEV_DIAGNOSTICS_INJECT` | `1` | `0` = 不将验证诊断注入下一轮上下文 |
| `BUTLER_CODING_STRICT` | `0` | `1` = CA4 严格模式；生产 pilot 类别（`deep`/`quick`/`nexus-sprint`/`lingwen-*` 等）若 `coding_knowledge.violated` 非空则 `success=false`（`CODING_STRICT_GATE`）。默认 `0` 不阻断 |
| `BUTLER_DEV_VERIFY_FIX_PIN` | `1` | `1` = verify 失败后将 `<dev-verify-feedback>` 置顶到最近 user 轮之前 |
| `BUTLER_GENTC_MUTATION_MIN_SCORE` | `0.6` | P-CT4a/H10：GenTC 变异测试得分下限（`evaluate_pct4a`） |
| `BUTLER_EXPERIENCE_MINING` | `1` | `0` = 关闭 D3-6 经验挖掘（含 runtime `builtin:experience_mining_weekly`） |
| `BUTLER_EXPERIENCE_MINING_AUTO_INGEST` | `0` | `1` = 高置信且定理通过时自动写入 `coding_experiences.json`；**runtime weekly job 固定不自动入库** |
| `BUTLER_EXPERIENCE_MINING_MIN_CONFIDENCE` | `0.7` | 自动入库置信度下限 |
| `BUTLER_EXPERIENCE_MINING_DAYS` | `7` | 近期文件扫描天数；runtime job `experience-mining-weekly` 使用同一窗口 |
| `BUTLER_EXPERIENCE_MERGE` | `1` | 经验写入前向量近邻消化（相似则融合或入队待审） |
| `BUTLER_EXPERIENCE_MERGE_AUTO` | `0.92` | 向量相似度 ≥ 此值且融合 LLM 成功 → 原地合并 |
| `BUTLER_EXPERIENCE_MERGE_REVIEW` | `0.78` | 相似度 ≥ 此值但未自动合并 → `metrics/experience_merge_pending.json` |
| `BUTLER_SKILL_FUSION` | `1` | Skill 相似合并使用可信模型（`auxiliary.fusion` 或 butler 栈） |

CLI：`butler memory merge-pending` 列出待审；`--apply KEY` / `--dismiss KEY` 应用或驳回（队列文件 `~/.butler/metrics/experience_merge_pending.json`）。

### 可观测（LangFuse）

> 部署指南：[`guides/langfuse-deployment.md`](../guides/langfuse-deployment.md)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_LANGFUSE_ENABLED` | `0` | `1` = 启用 LangFuse 追踪（需安装 `butler-system[observability]`）。生产部署：`bash scripts/butler-observability-provision.sh` |
| `BUTLER_PROJECT_NAME` | `butler-v4` | LangFuse 默认项目名（多项目见 [`langfuse-multi-project.md`](../guides/langfuse-multi-project.md)） |
| `BUTLER_EVAL_HARD_FEEDBACK` | `1` | `1` = 启用评估硬反馈（记忆半衰期调参、经验降权）；`0` 仅软反馈注入 |
| `BUTLER_EVAL_HARD_FEEDBACK_HOURS` | `1` | 硬反馈最小执行间隔（小时） |
| `BUTLER_EVAL_DEV_PASS_RATE_MIN` | `0.85` | 发版回归门 DevEngine（B1–B8）通过率下限 |
| `BUTLER_EVAL_MEM_PASS_RATE_MIN` | `0.7` | 发版回归门 Memory（MB1–MB7）通过率下限 |
| `BUTLER_EVAL_B9_IN_REGRESSION` | `1` | `0` = 发版回归门跳过 B9 oracle |
| `BUTLER_EVAL_B9_PASS_RATE_MIN` | `1.0` | B9 通过率下限（oracle 默认 2/2） |
| `BUTLER_EVAL_B9_RESCUE_PASS_RATE_MIN` | `0.5` | B9 LIVE 可解项通过率低于此值时自动 `adjust_delegate_rescue` 写入 `eval_overrides.json` |
| `BUTLER_EVAL_B9_TIER1_PASS_RATE_MIN` | `0.5` | B9 LIVE 发版门控：仅 Tier-1 可解项通过率下限（Tier-2 stretch 不阻塞） |
| `BUTLER_B9_TIER2_GATE_ENABLED` | `1` | `1` = 周循环 3-task probe 启用条件门控 |
| `BUTLER_B9_TIER2_GATE_MIN_PASSED` | `2` | Tier-2 probe 最低通过数（默认 2/3） |
| `BUTLER_B9_ORACLE_FEWSHOT` | `1` | `1` = B9 delegate 注入 oracle 金标 few-shot 修复范式 |
| `BUTLER_B9_LIVE_TUNING` | `1` | `1` = B9 LIVE 启用 delegate_rescue 覆盖 + b9-benchmark 类别；`0` = 关闭 |
| `BUTLER_EVAL_LLM_BENCHMARK` | `0` | `1` = B9 基准使用真实 `delegate_task`+LLM；`0` = oracle 模式（CI） |
| `BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES` | LangFuse 开则开 | `1`/`all` = 生产委派失败写入 `butler-delegate-failures`；`0` = 关闭 |
| `BUTLER_EVAL_SWE_LIVE_COUNT` | `3` | 每周 SWE-bench Lite LIVE 子集实例数（1–15） |
| `BUTLER_EVAL_SWE_GATE_MIN_WEEKS` | `2` | 全量 LIVE 入场需连续 N 周子集 100%（stretch：`1`） |
| `BUTLER_EVAL_DELEGATE_JUDGE` | `heuristic` | 委派完成启发式评分挂 trace；`off` = 关闭 |
| `BUTLER_MEMORY_METRICS_PERSIST` | `1` | `1` = 记忆效果度量 S_w/H_1/E_d 持久化到 `~/.butler/metrics/memory_metrics.json` |
| `LANGFUSE_HOST` | `http://localhost:3000` | LangFuse 服务地址（栈运维：`~/gongju/langfuse/ops.sh`） |
| `LANGFUSE_PUBLIC_KEY` | — | LangFuse 公钥（默认初始化 `pk-butler-dev`） |
| `LANGFUSE_SECRET_KEY` | — | LangFuse 私钥（默认初始化 `sk-butler-dev`） |

### D7 PIM 加密

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_PIM_ENCRYPT` | `0` | `1` = 启用 Fernet at-rest 加密（需安装 `cryptography`） |
| `BUTLER_PIM_ENCRYPT_KEY` | — | Fernet base64 密钥 |

### DE-GAP-2 自动验证

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_DEV_AUTO_VERIFY_LEVELS` | `lint,test` | 编辑后自动验证层级，逗号分隔。可选值：`lint`(V1)、`typecheck`(V2)、`test`(V3)、`integration`(V4)、`build`(V5)。也可通过 `verify_level_for_edit(files)` 按文件类型动态选取 |

### 运行环境与缓存

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_ENV` | — | `prod` / `staging` / `dev` / `test`；`prod`（或未知非空值）启用严格路径 — 见 [`security.md`](security.md) |
| `BUTLER_EXP_CACHE_TTL_SECONDS` | `60` | 实验性缓存 TTL（秒） |
| `BUTLER_TRANSPORT_CACHE_CONTROL` | — | transport 缓存控制头 |
| `BUTLER_TOKEN_COUNTER` | `heuristic` | Token 计数方式：`heuristic` / `tiktoken` / `tiktoken:<encoding>` |

### 网关内部

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_GATEWAY_HANDLER_SHUTDOWN_GRACE` | `30` | handler 关停宽限期（秒） |
| `BUTLER_GATEWAY_INFLIGHT_TTL_SEC` | `600` | inflight 幂等锁 TTL（秒） |

### 工具层补充

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_TOOL_PRUNE_PII_CHARS` | `200` | PII 脱敏保留字符数 |
| `BUTLER_TOOL_PRUNE_PIM_KEEP_RECENT` | `3` | PIM 工具保留最近 N 条 |

### OpenCode 集成

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_OPENCODE_ENABLED` | `0` | `1` = 启用 OpenCode 集成 |
| `BUTLER_OPENCODE_MODE` | `subprocess` | `subprocess` / `http` / `mcp` |
| `BUTLER_OPENCODE_BIN` | `opencode` | OpenCode 可执行文件路径 |
| `BUTLER_OPENCODE_URL` | `http://127.0.0.1:4096` | OpenCode HTTP 端点 |
| `BUTLER_OPENCODE_PASSWORD` | — | OpenCode HTTP 认证密码 |
| `BUTLER_OPENCODE_TIMEOUT` | `600` | OpenCode 超时（秒） |
| `BUTLER_OPENCODE_AGENT` | `build` | OpenCode agent 类型：`build` / `plan` |
| `BUTLER_OPENCODE_MODEL` | — | OpenCode 模型，例如 `anthropic/claude-sonnet-4-20250514` |

## 相关

- [`../guides/project-onboarding.md`](../guides/project-onboarding.md)  
- [`../plans/consolidation-2026-05.md`](../plans/archive/consolidation-2026-05.md)
