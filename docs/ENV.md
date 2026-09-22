# Butler v5 — Environment Variables Inventory

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計) | **读者**: Owner / Self-hosting admin / Integrator
> **关系**:
> - 功能视角 → [`FEATURES.md`](FEATURES.md)
> - HTTP/WS API surface → [`API_ENDPOINTS.md`](API_ENDPOINTS.md)
> - 目标架构 → [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §16 (部署)
> - 自托管完整路径（env 填写 + docker + demo）→ [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md)
> - 生产加固（secrets + 容器 + 网络）→ [`deployment/production-hardening.md`](deployment/production-hardening.md)
> - v5 env example → [`../butler-v5/.env.example`](../butler-v5/.env.example)
> - 历史 v4 reference → [`config/reference.md`](config/reference.md)（**v4**；本表只覆盖 v5 `BUTLER_V5_*`）

> **范围**: 本表仅覆盖 **`BUTLER_V5_*` 前缀**（butler-v5 实际读取）。v4 的 `BUTLER_*` 由 [`config/reference.md`](config/reference.md) 覆盖（v4 已退役）。

---

## 图例

- ✅ **必填**（生产环境无默认 / 缺失 fail-closed）
- 🟡 **选填**（有合理 default；0/空 = 关闭）
- 📅 **stub**（handler 接了 env 但当前 disabled / 触发条件未达）
- ❌ **legacy**（保留兼容；新代码勿依赖）

## §1 Server / Working Set

> DESIGN §16（单机自托管模块化单体）。DB = Postgres 生产 / PGlite demo。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `DATABASE_URL` | string | `postgres://butler:butler@localhost:5432/butler_v5` | Postgres DSN；`BUTLER_V5_DB=postgres` 时启用 | [`packages/persistence/src/runtime-store.ts`](../butler-v5/packages/persistence/src/runtime-store.ts), DESIGN §16 | ✅ (生产) |
| `BUTLER_V5_DB` | enum | `pglite` | `postgres` \| `pglite`；`postgres` 需 `DATABASE_URL` | [`apps/api/src/wiring.ts`](../butler-v5/apps/api/src/wiring.ts) | 🟡 |
| `BUTLER_V5_PGLITE_DATA_DIR` | path | `~/.butler/v5-data` | PGlite 落盘；`memory` / `:memory:` 强制内存 | [`packages/persistence/src/memory/runtime-store.ts`](../butler-v5/packages/persistence/src/memory/runtime-store.ts) | 🟡 |
| `BUTLER_V5_READ_MODEL` | enum | `relational` | `event_store` \| `hybrid` \| `relational` | `wiring.ts` | 🟡 |
| `BUTLER_V5_WORKSPACE_ROOT` | path | cwd | `read_file` / `run_command` 工作区根 | [`apps/api/src/workspace-tools.ts`](../butler-v5/apps/api/src/workspace-tools.ts) | ✅ (D77 T6 harden) |
| `BUTLER_V5_WORKING_SET_MAX_CHARS` | int | 20000 | 单 Run working set 字符上限 | [`packages/runtime/src/working-set.ts`](../butler-v5/packages/runtime/src/working-set.ts), DESIGN §6.1 | 🟡 |
| `BUTLER_V5_WORKING_SET_MAX_MESSAGES` | int | 50 | working set 消息条数上限 | `working-set.ts` | 🟡 |
| `BUTLER_V5_DEV_WORKING_SET_MAX_CHARS` | int | 同上 | dev role 专属 working set 上限 | `working-set.ts` | 🟡 |
| `BUTLER_V5_DEV_WORKING_SET_MAX_MESSAGES` | int | 同上 | dev role 专属 | `working-set.ts` | 🟡 |
| `NODE_ENV` | enum | `development` | `production` 强制 Postgres + 严格路径 | `Dockerfile` (D77 T1) | ✅ (prod) |

## §2 Inbound / Channel API

> DESIGN §8 channel-webhook. 单 secret 入口 + 可选 channel 边界 allowlist。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_INBOUND_SHARED_SECRET` | string | `test-inbound-secret-9c2f` (demo) | `/v1/wechat/inbound` + `/v1/channel/inbound` + `/v1/ws/subscribe` 的 `x-inbound-secret` 校验；**生产必填且覆盖 demo 默认** | [`apps/api/src/routes/inbound.ts`](../butler-v5/apps/api/src/routes/inbound.ts), [`routes/ws-subscribe.ts`](../butler-v5/apps/api/src/routes/ws-subscribe.ts) | ✅ (生产) |
| `BUTLER_V5_CHANNEL_INBOUND_SECRET` | string | 同上 alias | 通道内独立 secret（备用 alias） | [`apps/api/src/routes/inbound.ts:202`](../butler-v5/apps/api/src/routes/inbound.ts) | 🟡 |
| `BUTLER_V5_CHANNEL_API_ENABLED` | bool | `0` | `1` 启用 `POST /v1/channel/inbound` | [`apps/api/src/routes/inbound.ts`](../butler-v5/apps/api/src/routes/inbound.ts) | 🟡 |
| `BUTLER_V5_CHANNEL_ALLOWLIST` | csv | `[]` | 允许的 `channelId` 列表（空=不限制） | `routes/inbound.ts` | 🟡 |
| `BUTLER_V5_CHANNEL_OUTBOUND_MEDIA` | bool | `0` | `1` 时解析回复 `[[media:path]]` 经 Slack `files.upload` / Telegram `sendPhoto` 出站 | [`apps/api/src/channel-outbound-media.ts`](../butler-v5/apps/api/src/channel-outbound-media.ts) | 🟡 |
| `BUTLER_V5_INBOUND_ALLOW_PRIVATE_HOSTS` | bool | `0` | `1` 时允许 iLink 解析内网 host | `apps/api/src/ilink-config.ts` | 🟡 |

## §3 WeChat (iLink + state)

> DESIGN §8 Channel WeChat canonical driving adapter。iLink 长轮询是默认通道。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_ILINK_ENABLED` | bool | `0` | `1` 启用原生 iLink long-poll（需 `WECHAT_TOKEN`） | [`apps/api/src/ilink-config.ts`](../butler-v5/apps/api/src/ilink-config.ts) | ✅ |
| `BUTLER_V5_ILINK_INBOUND_TIMEOUT_MS` | int | — | iLink 入站处理超时 | `ilink-config.ts` | 🟡 |
| `BUTLER_V5_ILINK_LONG_POLL_MS` | int | — | iLink 长轮询间隔 | `ilink-config.ts` | 🟡 |
| `BUTLER_V5_ILINK_PING_TO` | int | — | iLink ping 超时 | `ilink-config.ts` | 🟡 |
| `BUTLER_V5_ILINK_EMPTY_DELAY_MS` | int | — | iLink 空轮询延迟 | `ilink-config.ts` | 🟡 |
| `BUTLER_V5_ILINK_SESSION_SLEEP_MS` | int | — | iLink session sleep | `ilink-config.ts` | 🟡 |
| `BUTLER_V5_ILINK_SYNC_BUF_PATH` | path | — | iLink 同步 buffer 路径 | `ilink-sync.ts` | 🟡 |
| `WECHAT_TOKEN` | string | — | iLink 长轮询 token（与 v4 共用 env） | `ilink-config.ts`, DESIGN §7.1 | ✅ (生产) |
| `BUTLER_V5_WECHAT_SESSION_STATE` | path | — | wechat session state 持久化 | [`apps/api/src/wechat-session-state.ts`](../butler-v5/apps/api/src/wechat-session-state.ts) | 🟡 |
| `BUTLER_V5_WECHAT_ACTIVE_PROJECT_STORE` | path | — | active project store 路径 | [`apps/api/src/wechat-active-project.ts`](../butler-v5/apps/api/src/wechat-active-project.ts) | 🟡 |
| `BUTLER_V5_WECHAT_PROJECT_PATHS` | csv | — | wechat project paths 列表 | [`apps/api/src/wechat-project-switch.ts`](../butler-v5/apps/api/src/wechat-project-switch.ts) | 🟡 |
| `BUTLER_V5_WECHAT_TOOL_ALLOWLIST` | csv | — | wechat tool allowlist（覆盖 default） | [`apps/api/src/wechat-tool-profile.ts`](../butler-v5/apps/api/src/wechat-tool-profile.ts) | 🟡 |
| `BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH` | path | — | wechat tool allowlist 文件路径 | `wechat-tool-profile.ts` | 🟡 |
| `WECHAT_APP_ID` | string | — | 微信 AppID（v4 compat） | `.env.example` | 🟡 |
| `WECHAT_APP_SECRET` | string | — | 微信 AppSecret（v4 compat） | `.env.example` | 🟡 |

## §4 Slack

> D63 T3 SEC-006 Slack signing secret fail-closed + D71 T4 SEC-004 user allowlist。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_SLACK_ENABLED` | bool | `0` | `1` 启用 `POST /v1/channel/slack/events` | [`apps/api/src/routes/slack-events.ts`](../butler-v5/apps/api/src/routes/slack-events.ts) | ✅ |
| `BUTLER_V5_SLACK_SIGNING_SECRET` | string | — | Slack HMAC 签名密钥；生产必填（fail-closed） | `routes/slack-events.ts`, DESIGN §16 | ✅ (生产) |
| `BUTLER_V5_SLACK_BOT_TOKEN` | secret | — | Slack Bot token；设置后 webhook 自动 `chat.postMessage` 出站 | [`apps/api/src/channel-config.ts`](../butler-v5/apps/api/src/channel-config.ts) | ✅ (生产) |
| `BUTLER_V5_SLACK_USER_ID_ALLOWLIST` | csv | — | Slack user 允许列表（D71 T4 SEC-004 实证） | `routes/slack-events.ts` | ✅ |

## §5 Telegram

> 📅 route 已注册但无 adapter dir（DESIGN §18 not trigger）。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_TELEGRAM_ENABLED` | bool | `0` | `1` 启用 `POST /v1/channel/telegram/webhook` | [`apps/api/src/routes/telegram-webhook.ts`](../butler-v5/apps/api/src/routes/telegram-webhook.ts) | 📅 |
| `BUTLER_V5_TELEGRAM_WEBHOOK_SECRET` | string | — | Telegram `X-Telegram-Bot-Api-Secret-Token` 校验 | `routes/telegram-webhook.ts` | 📅 |
| `BUTLER_V5_TELEGRAM_BOT_TOKEN` | secret | — | Telegram Bot token；设置后 webhook 自动 `sendMessage` 出站 | `channel-config.ts` | 📅 |
| `BUTLER_V5_TELEGRAM_USER_ID_ALLOWLIST` | csv | — | Telegram user allowlist（D71 T4 SEC-005） | `routes/telegram-webhook.ts` | 📅 |
| `BUTLER_V5_TELEGRAM_MEDIA_CACHE` | bool | `0` | `1` 时入站 media 下载本地 | `routes/telegram-webhook.ts` | 📅 |
| `BUTLER_V5_TELEGRAM_MEDIA_DIR` | path | `./.butler-v5/telegram-media` | Telegram 媒体缓存目录 | `routes/telegram-webhook.ts` | 📅 |
| `BUTLER_V5_TELEGRAM_MEDIA_MAX_BYTES` | int | `8388608` | 单文件下载上限 | `routes/telegram-webhook.ts` | 🟡 |

## §6 LLM / Model Port + Pricing

> DESIGN §6.2 (5-tag Decision) + §14 (14 fields observability) + D44 P5 Model Port。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_MODEL_PLAN` | string | — | plan role 模型（5-tag Decision） | [`packages/ports/src/core/model-port.ts`](../butler-v5/packages/ports/src/core/model-port.ts) | ✅ |
| `BUTLER_V5_MODEL_EXEC` | string | — | exec role 模型 | `model-port.ts` | ✅ |
| `BUTLER_V5_MODEL_INTAKE` | string | — | intake role 模型 | `model-port.ts` | ✅ |
| `BUTLER_V5_LLM_TIMEOUT_MS` | int | `30000` | LLM 调用超时 | [`packages/runtime/src/conversation-loop.ts`](../butler-v5/packages/runtime/src/conversation-loop.ts), DESIGN §6.2 | 🟡 |
| `BUTLER_V5_LLM_FIXTURE_DIR` | path | — | 脚本化 LLM fixture dir（demo 用） | [`tests/acceptance/harness/`](../butler-v5/tests/acceptance/harness/) | 🟡 |
| `BUTLER_V5_DEEPSEEK_THINKING` | bool | `0` | DeepSeek thinking 协议开关 | `model-router.ts` | 🟡 |
| `BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK` | float | `null` | 模型输入价格 USD/Mtoken；缺 = `costUsd=null` | [`apps/api/src/llm-pricing.ts`](../butler-v5/apps/api/src/llm-pricing.ts), DESIGN §14 | 🟡 |
| `BUTLER_V5_PRICING_<MODEL>_OUTPUT_PER_MTOK` | float | `null` | 模型输出价格 USD/Mtoken | `llm-pricing.ts` | 🟡 |
| `ANTHROPIC_API_KEY` | secret | — | Anthropic API key（demo 可空） | [`butler-v5/README.md`](../butler-v5/README.md) | ✅ (生产) |
| `OPENAI_API_KEY` | secret | — | OpenAI API key | `model-router.ts` | 🟡 |
| `DEEPSEEK_API_KEY` | secret | — | DeepSeek API key | `model-router.ts` | 🟡 |
| `DASHSCOPE_API_KEY` | secret | — | DashScope (Qwen) API key | `model-router.ts` | 🟡 |

## §7 MCP

> DESIGN §9 Capability + MCP thin client。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_MCP_ENABLED` | bool | `0` | `1` 注册 MCP 工具（走 PolicyGate + 审批；默认 off） | [`apps/api/src/mcp-bootstrap.ts`](../butler-v5/apps/api/src/mcp-bootstrap.ts), DESIGN §18 条件准入 | ✅ |
| `BUTLER_V5_MCP_TRANSPORT` | enum | `http` | `http` \| `sse` \| `stdio` | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_TOOL_NAMES` | csv | — | MCP stub 工具名（未接 URL/stdio 时） | `mcp-bootstrap.ts` | 🟡 |
| `BUTLER_V5_MCP_URL` | string | — | MCP HTTP/SSE JSON-RPC 端点 | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_COMMAND` | string | — | MCP stdio 可执行 | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_ARGS` | csv | — | MCP stdio 参数 | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_TOKEN` | secret | — | MCP HTTP/SSE Bearer token | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_TIMEOUT_MS` | int | `30000` | MCP 传输超时 | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_REQUIRED` | bool | `0` | `1` 时 bootstrap 失败拒绝启动 | `mcp-bootstrap.ts` | 🟡 |
| `BUTLER_V5_MCP_REQUIRE_CONSENT` | bool | `0` | `1` 时仅 bootstrap `BUTLER_V5_MCP_CONSENT` 列出的 server | `mcp-bootstrap.ts` | 🟡 |
| `BUTLER_V5_MCP_CONSENT` | csv | — | 已 consent 的 MCP server id | `mcp-bootstrap.ts` | 🟡 |
| `BUTLER_V5_MCP_SERVER_ID` | string | — | 显式 server id（覆盖 URL hostname 推导） | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_MANIFEST_PATH` | path | — | MCP manifest JSON；设置后校验 server id 必须声明 | [`apps/api/src/mcp-manifest.ts`](../butler-v5/apps/api/src/mcp-manifest.ts) | 🟡 |
| `BUTLER_V5_MCP_ALLOW_PRIVATE_HOSTS` | bool | `0` | MCP HTTP/SSE 是否允许内网 host | `mcp-config.ts` | 🟡 |
| `BUTLER_V5_MCP_READONLY_AUTO_ALLOW` | bool | `0` | MCP readonly 工具自动允许 | [`apps/api/src/mcp-readonly-policy.ts`](../butler-v5/apps/api/src/mcp-readonly-policy.ts) | 🟡 |

## §8 Subagent

> DESIGN §4.2 Child Run + delegate-runtime。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_SUBAGENT_ENABLED` | bool | `0` | `1` 启用 background subagent（loopback WS + outbox worker + `delegate_to_subagent` 工具） | [`apps/api/src/subagent-config.ts`](../butler-v5/apps/api/src/subagent-config.ts) | ✅ |
| `BUTLER_V5_SUBAGENT_AUDIT_PATH` | path | `~/.config/butler-v5/audit/subagent.jsonl` | Subagent JSONL 审计 | `subagent-config.ts` | 🟡 |
| `BUTLER_V5_SUBAGENT_WORKER_INTERVAL_MS` | int | — | subagent worker tick 间隔 | [`apps/api/src/subagent-worker.ts`](../butler-v5/apps/api/src/subagent-worker.ts) | 🟡 |
| `WS_PORT` | int | `3001` | subagent loopback WS port | `subagent-config.ts` | 🟡 |
| `BUTLER_V5_DEV_SESSION_GRANT_MINUTES` | int | — | dev session grant TTL | [`apps/api/src/dev-session-grant.ts`](../butler-v5/apps/api/src/dev-session-grant.ts) | 🟡 |
| `BUTLER_V5_DEV_SESSION_MAX_USES` | int | — | dev session grant 最大使用次数 | `dev-session-grant.ts` | 🟡 |
| `BUTLER_V5_DEV_DIRECT_EXEC` | bool | `0` | dev role 直接 exec（绕过 chain） | `dev-session-grant.ts` | 🟡 |

## §9 Memory / Durable

> DESIGN §12 G1-G5 治理链路（已 ship D39-D43）。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_DURABLE` | bool | `0` | `1` 启用 durable memory migration（表始终迁移） | [`apps/api/src/durable-memory-inject.ts`](../butler-v5/apps/api/src/durable-memory-inject.ts) | 🟡 |
| `BUTLER_V5_DURABLE_MEMORY` | bool | `0` | `1` 将 **confirmed** memory 注入 Loop working set | `durable-memory-inject.ts` | 🟡 |
| `BUTLER_V5_AUTO_PROMOTE_ENABLED` | bool | `0` | `1` 启用 G4 candidate 3d auto-promote sweeper | [`apps/api/src/auto-promote-config.ts`](../butler-v5/apps/api/src/auto-promote-config.ts) | 🟡 |
| `BUTLER_V5_AUTO_PROMOTE_WINDOW_DAYS` | int | `3` | G4 promote 前等待天数 | `auto-promote-config.ts` | 🟡 |
| `BUTLER_V5_AUTO_PROMOTE_ROLLBACK_WINDOW_DAYS` | int | `7` | G4 owner 撤销窗口 | `auto-promote-config.ts` | 🟡 |
| `BUTLER_V5_AUTO_PROMOTE_SWEEP_INTERVAL_HOURS` | int | — | sweeper tick 间隔（小时） | [`apps/api/src/auto-promote-sweeper.ts`](../butler-v5/apps/api/src/auto-promote-sweeper.ts) | 🟡 |
| `BUTLER_V5_AUTO_PROMOTE_SWEEP_LIMIT` | int | — | sweeper 单 tick 处理上限 | `auto-promote-sweeper.ts` | 🟡 |
| `BUTLER_V5_CANDIDATE_EXPIRES_ENABLED` | bool | `0` | `1` 启用 G1 stale candidate expire sweeper | [`apps/api/src/candidate-expires-sweeper.ts`](../butler-v5/apps/api/src/candidate-expires-sweeper.ts) | 🟡 |
| `BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS` | int | `604800000` (7d) | G1 stale 阈值 | `candidate-expires-sweeper.ts` | 🟡 |
| `BUTLER_V5_CANDIDATE_EXPIRES_INTERVAL_MS` | int | — | G1 sweeper tick | `candidate-expires-sweeper.ts` | 🟡 |
| `BUTLER_V5_CANDIDATE_EXPIRES_BATCH_LIMIT` | int | — | G1 sweeper 单 tick 处理上限 | `candidate-expires-sweeper.ts` | 🟡 |
| `BUTLER_V5_MEMORY_DEDUP_ENABLED` | bool | `0` | `1` 启用 G2 trigram Jaccard dedup | [`apps/api/src/dedup-config.ts`](../butler-v5/apps/api/src/dedup-config.ts) | 🟡 |
| `BUTLER_V5_MEMORY_DEDUP_THRESHOLD` | float | `0.85` | G2 dedup 阈值 | `dedup-config.ts` | 🟡 |
| `BUTLER_V5_MEMORY_DEDUP_LIMIT` | int | — | G2 dedup 候选上限 | `dedup-config.ts` | 🟡 |
| `BUTLER_V5_MEMORY_DEDUP_RECENT_MS` | int | — | G2 dedup 候选时间窗 | `dedup-config.ts` | 🟡 |

## §10 Sandbox / Workspace / Network

> DESIGN §10.4 Sandbox profile + §18 (R16 bubblewrap partial)。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_SANDBOX` | enum | unset | unset = 进程内约束；`bubblewrap` = bwrap 隔离（缺 bwrap 时 fail-closed） | [`apps/api/src/sandbox-config.ts`](../butler-v5/apps/api/src/sandbox-config.ts), DESIGN §10.4 | 🟡 |
| `BUTLER_V5_SANDBOX_WORKSPACE_ROOT` | path | — | bwrap 沙箱 workspace 根 | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS` | bool | `0` | `1` 时 Owner 审批 `networkAllowlist` 可含内网 | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_NETWORK_MODE` | enum | `binary` | `allowlist` 启用 P2c egress proxy | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_EGRESS_ISOLATION` | enum | `proxy` | `slirp` 启用 P2d（unshare + slirp4netns） | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY` | string | — | host 需经系统代理出网时 CONNECT | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_SLIRP_FALLBACK` | bool | `0` | slirp 失败时降级策略 | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_SANDBOX_MAX_FILE_BYTES` | int | — | bwrap 内单文件大小上限 | `sandbox-config.ts` | 🟡 |
| `BUTLER_V5_GRANT_NETWORK_HOSTS` | csv | — | 审批 ScopedGrant 时额外允许的出站 host；MCP 能力自动合并 `MCP_URL` hostname | [`packages/runtime/src/policy-gate.ts`](../butler-v5/packages/runtime/src/policy-gate.ts), DESIGN §10.3 | 🟡 |
| `BUTLER_V5_RUN_COMMAND_CREDENTIALS` | json | — | run_command 注入凭证（fail-closed） | [`packages/adapters/src/credentials/host-credentials.ts`](../butler-v5/packages/adapters/src/credentials/host-credentials.ts) | 🟡 |

## §11 Schedule / Loop / Decoder

> DESIGN §6.2 (5-tag + decoder retry) + §18 (Schedule trigger-conditioned)。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_SCHEDULE_ENABLED` | bool | `0` | `1` 启用 schedule worker | [`apps/api/src/schedule-config.ts`](../butler-v5/apps/api/src/schedule-config.ts) | 🟡 |
| `BUTLER_V5_SCHEDULE_DEFER_WHEN_BUSY` | bool | `0` | `1` 时 Run 忙则推迟 schedule | `schedule-config.ts` | 🟡 |
| `BUTLER_V5_SCHEDULE_TICK_MS` | int | — | schedule tick 间隔 | [`apps/api/src/schedule-worker.ts`](../butler-v5/apps/api/src/schedule-worker.ts) | 🟡 |
| `BUTLER_V5_SCHEDULE_JOBS` | csv | — | 静态 schedule jobs（逗号分隔） | `schedule-config.ts` | 🟡 |
| `BUTLER_V5_SCHEDULE_JOBS_PATH` | path | — | schedule jobs 文件路径（YAML） | `schedule-config.ts` | 🟡 |
| `BUTLER_V5_MAX_DECODE_RETRIES` | int | `1` | decoder 失败最大重试 | [`packages/runtime/src/conversation-loop.ts`](../butler-v5/packages/runtime/src/conversation-loop.ts), DESIGN §6.2 line 269 | 🟡 |
| `BUTLER_V5_KILL_SWITCH` | bool | `0` | `1` 启用全局 kill switch（拒绝新 Run） | [`apps/api/src/kill-switch.ts`](../butler-v5/apps/api/src/kill-switch.ts) | 🟡 |
| `BUTLER_V5_STUCK_LOOP_THRESHOLD` | int | — | Run stuck 检测阈值 | [`packages/runtime/src/run-engine.ts`](../butler-v5/packages/runtime/src/run-engine.ts) | 🟡 |
| `BUTLER_V5_POST_APPROVAL_LOOP` | bool | `0` | `1` 审批后 Run 自动继续 | `run-engine.ts` | 🟡 |

## §12 Owner Rate Limit / WS Auth

> D70 T4 SEC-002 owner rate-limit 闭环 + D63 T3 SEC-019 WS subscribe cap。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_OWNER_RATE_LIMIT_MAX` | int | `120` | owner rate-limit 在 window 内最大请求数 | [`apps/api/src/lib/owner-rate-limit.ts`](../butler-v5/apps/api/src/lib/owner-rate-limit.ts) | 🟡 |
| `BUTLER_V5_OWNER_RATE_LIMIT_WINDOW_MS` | int | `60000` | owner rate-limit 时间窗（毫秒） | `owner-rate-limit.ts` | 🟡 |
| `BUTLER_V5_WS_ALLOWED_ORIGINS` | csv | — | WebSocket subscribe Origin 白名单 | [`apps/api/src/routes/ws-subscribe.ts`](../butler-v5/apps/api/src/routes/ws-subscribe.ts) | 🟡 |

## §13 Sweeper / Task Run / Session Digest

> P3 wechat task digest + C wechat sweeper push + D44 task-run。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_SWEEPER_NOTIFY_ENABLED` | bool | `0` | `1` 启用 wechat sweeper push（C `68dc2bbe`） | [`apps/api/src/wechat-sweeper-notify.ts`](../butler-v5/apps/api/src/wechat-sweeper-notify.ts) | 🟡 |
| `BUTLER_V5_SWEEPER_NOTIFY_OWNER` | string | — | sweeper 推送给 owner user id | `wechat-sweeper-notify.ts` | 🟡 |
| `BUTLER_V5_SWEEPER_NOTIFY_THROTTLE_MS` | int | `3600000` (1h) | sweeper throttle 间隔（毫秒） | `wechat-sweeper-notify.ts` | 🟡 |
| `BUTLER_V5_SESSION_DIGEST_IDLE_MS` | int | — | session-open digest idle 阈值 | [`apps/api/src/wechat-session-digest.ts`](../butler-v5/apps/api/src/wechat-session-digest.ts) | 🟡 |
| `BUTLER_V5_TASK_RUN_ASYNC` | bool | `0` | task run 异步执行 | [`apps/api/src/task-run-background.ts`](../butler-v5/apps/api/src/task-run-background.ts) | 🟡 |

## §14 Dev / CI / Test / Inline Approval

> D-series audit gate methodology check (M15 docker-deploy) + dev tooling。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_CI_SMOKE` | bool | `0` | CI smoke 模式（精简 fixture） | [`apps/api/src/dev-quality-gate.ts`](../butler-v5/apps/api/src/dev-quality-gate.ts) | 🟡 |
| `BUTLER_V5_DEV_VERIFY_ENABLED` | bool | `0` | dev role edit 后自动 verify | [`apps/api/src/dev-verify.ts`](../butler-v5/apps/api/src/dev-verify.ts) | 🟡 |
| `BUTLER_V5_DEV_VERIFY_CMD` | string | — | dev verify 命令覆盖 | `dev-verify.ts` | 🟡 |
| `BUTLER_V5_DEV_VERIFY_INLINE` | bool | `0` | dev verify inline 输出 | `dev-verify.ts` | 🟡 |
| `BUTLER_V5_DEV_VERIFY_TIMEOUT_MS` | int | — | dev verify 单步超时 | `dev-verify.ts` | 🟡 |
| `BUTLER_V5_TEST_DATABASE_URL` | string | — | 测试专用 DB | `butler-v5/vitest.config.ts` | 🟡 |
| `BUTLER_V5_TEST_FULL_SANDBOX` | bool | `0` | 测试用 full sandbox（bwrap） | `vitest.config.ts` | 🟡 |
| `BUTLER_V5_INTAKE_ENABLED` | bool | `0` | intake path 启用 | [`apps/api/src/wechat-intake-llm.ts`](../butler-v5/apps/api/src/wechat-intake-llm.ts) | 🟡 |
| `BUTLER_V5_INTAKE_LLM` | bool | `0` | intake 用 LLM | `wechat-intake-llm.ts` | 🟡 |

## §15 Tracing / OTEL / Misc

> DESIGN §14 observability + DESIIGN §18 OTEL deferred。

| 变量 | 类型 | 默认 | 用途 | Source 指针 | 状态 |
|------|------|------|------|------------|------|
| `BUTLER_V5_TRACE` | bool | `0` | `1` 启用本地 trace | [`apps/api/src/trace.ts`](../butler-v5/apps/api/src/trace.ts) | 🟡 |
| `BUTLER_V5_TRACE_MAX_EVENTS` | int | — | trace 单 Run 事件数上限 | `trace.ts` | 🟡 |
| `BUTLER_V5_TRACE_REDACT` | csv | — | trace redaction 字段（csv） | `trace.ts` | 🟡 |
| `BUTLER_V5_OTEL_EXPORTER` | enum | unset | OTEL exporter（unset = 不启用） | `trace.ts`, DESIGN §18 deferred | 📅 |
| `BUTLER_V5_ENV_FILE` | path | `.env` | env file 路径覆盖 | [`apps/api/src/env-util.ts`](../butler-v5/apps/api/src/env-util.ts) | 🟡 |
| `BUTLER_V5_ENV_PATH` | path | — | env file 搜索路径 | `env-util.ts` | 🟡 |
| `BUTLER_V5_LLM_FIXTURE_DIR` | path | — | LLM fixture 目录（demo） | `harness/` | 🟡 |

## §16 总览 / 统计

| § | 类别 | env 数 |
|---|------|--------|
| §1 | Server / Working Set | 10 |
| §2 | Inbound / Channel API | 6 |
| §3 | WeChat (iLink + state) | 14 |
| §4 | Slack | 4 |
| §5 | Telegram | 7 |
| §6 | LLM / Model Port + Pricing | 12 |
| §7 | MCP | 14 |
| §8 | Subagent | 7 |
| §9 | Memory / Durable | 15 |
| §10 | Sandbox / Workspace / Network | 10 |
| §11 | Schedule / Loop / Decoder | 9 |
| §12 | Owner Rate Limit / WS Auth | 3 |
| §13 | Sweeper / Task Run / Session Digest | 5 |
| §14 | Dev / CI / Test / Inline Approval | 8 |
| §15 | Tracing / OTEL / Misc | 7 |
| **Total** | — | **131 env vars (BUTLER_V5_*)** |

## §17 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单 | [`FEATURES.md`](FEATURES.md) |
| API endpoint 清单 | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| 自托管指南（env 填写 + docker） | [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) |
| 生产加固（secrets + 容器 + 网络） | [`deployment/production-hardening.md`](deployment/production-hardening.md) |
| 目标架构 §16 部署 | [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) |
| v5 env example 模板 | [`../butler-v5/.env.example`](../butler-v5/.env.example) |
| v4 reference（legacy） | [`config/reference.md`](config/reference.md) |

---

**End of ENV.md** | D80 cycle 26 inventory batch | **131 env vars / 1 prefix (`BUTLER_V5_*`)** | 仅覆盖 v5 实读；v4 `BUTLER_*` 见 `config/reference.md`