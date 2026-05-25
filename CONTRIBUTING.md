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

- 微信：`/计划`、`/执行`、`/任务`；`/诊断` 含上下文用量档位、Shell hooks 摘要、**出站策略**（完成推送/委派模式/冷却）；`/状态` 含规划模式
- 可选环境变量：`BUTLER_DISABLE_AUTO_COMPACT`、`BUTLER_CONTEXT_*`、`BUTLER_MEMORY_MAX_LINES`
- 大工具结果落盘：`BUTLER_TOOL_RESULT_SPILL`（默认开）→ `~/.butler/sessions/<session>/tool-results/`；上下文为 `<persisted-output>` 指针，需完整内容时用 `read_file`
- 工具分级剪枝：`BUTLER_TOOL_PRUNE_*`；压缩后 `post_compact` 重注入 MEMORY/任务锚点；`/诊断` 含 **上轮循环结束**（`loop_transition_reason`）
- **发版后真机抽测（约 10 分钟）**：[`docs/guides/wechat-daily-smoke-checklist.md`](docs/guides/wechat-daily-smoke-checklist.md#线束与长任务完成提醒发版后建议-10-分钟) 表 **H1–H10**（规划、Hooks、委派完成推送、progress ack、入队 drain）

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

环境变量：`BUTLER_GATEWAY_COMPLETION_NOTIFY`（总开关）、`BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS`（默认 90）、`BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY`、`BUTLER_GATEWAY_TURN_COMPLETION_NOTIFY`、`BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY`。

完成推送与 `runtime` 定时推送共用 `BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS` 冷却；发送失败（含限流/网络）时写入 `runtime/push_queue.jsonl`，由 `drain_push_queue` / runtime due 重试。工作流异常结束也会尝试推送失败摘要。

委派完成推送模式：`BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE`（默认 `last` 仅最后一次委派；`each` 最多 `BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH` 次；`once` 仅第一次）。Gateway 处理超时且曾发 progress ack 时可推 `BUTLER_GATEWAY_TIMEOUT_COMPLETION_NOTIFY`。Shell hooks：`SubagentStop` 在委派结束触发。

`/诊断` 另含 **出站推送本轮**（成功/失败/入队）与 **推送队列待发** 条数；`/新对话` 会重置 hook 与出站遥测。变量模板见仓库根 [`.env.example`](.env.example)；运维说明见 [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md)。真机步骤见上节 **H1–H10** 表。
