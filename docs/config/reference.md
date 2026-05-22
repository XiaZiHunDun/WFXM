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
