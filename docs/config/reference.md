# Butler 配置参考（env + YAML）

> 密钥与部署覆盖放 `.env`；模型与网关默认见 `docs/config/config.yaml.example` → `~/.butler/config.yaml`。  
> 完整示例：仓库根 `.env.example`。

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

## 冒烟 / 开发

| 变量 | 说明 |
|------|------|
| `BUTLER_WECHAT_DEV_SMOKE` | `/诊断` 显示开发项 |
| `BUTLER_CLI_STREAM_MODE` | CLI 流式 `live` / `off` |
| `BUTLER_RUNTIME_RUN_CONSISTENCY` | `1` 时 runtime-smoke 跑 consistency-weekly |

## 相关

- [`../guides/project-onboarding.md`](../guides/project-onboarding.md)  
- [`../plans/consolidation-2026-05.md`](../plans/consolidation-2026-05.md)
