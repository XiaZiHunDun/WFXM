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

设计说明见 `docs/plans/corpus-testing-module-design-2026-05.md` 与 `tests/corpus/suites/wechat_real/lw_real/meta.yaml`。

## Butler 线束（规划 / 上下文 / Hooks）

- 微信：`/计划`、`/执行`、`/任务`；`/诊断` 含上下文用量档位；`/状态` 含规划模式
- 可选环境变量：`BUTLER_DISABLE_AUTO_COMPACT`、`BUTLER_CONTEXT_*`、`BUTLER_MEMORY_MAX_LINES`

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
| `Stop` | 单轮 AgentLoop 结束（`matcher` 匹配 `status`: `completed` / `interrupted` / `error` / `tool_limit`） |
