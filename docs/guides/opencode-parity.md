# OpenCode 对标能力 — 运维速查

> 对照 [`plans/opencode-butler-comparison-report-2026-05.md`](../plans/comparisons/opencode-butler-comparison-report-2026-05.md) 已落地的 Butler 子集。  
> **主场景**：微信网关 + 本地工具沙箱；**不做**：OpenCode HTTP 多客户端、公开 Share、完整 snapshot revert。

更新：2026-05-25

---

## 微信 Slash 命令（Owner 敏感项标注）

| 命令 | 说明 | Owner |
|------|------|-------|
| `/帮助` | 常用命令摘要 | 否 |
| `/导出 [行数]` | 会话 transcript → Markdown；微信下附带发 `.md` 文件 | **是** |
| `/回滚 [保留行数]` | 仅截断 `transcript.jsonl`（非 git snapshot） | **是** |
| `/fork-transcript N`、`/分叉 N` | 从第 N 条 `type=user` 行保留 transcript（Codex C2-3） | **是** |
| `/记忆提炼 [项目]` | 从 transcript 提炼记忆（需 `BUTLER_TRANSCRIPT_MEMORY=1`） | **是** |
| `/批准一次` | 本次会话内批准 pending 权限 | **是** |
| `/始终允许 <权限>` | 写入批准缓存（TTL 见 env） | **是** |
| `/权限` | 查看待批准项 | **是** |
| `/任务` | 最近 `delegate_task` 任务列表 | 否 |
| `/待办` | 会话 todos | 否 |
| `/状态` `/诊断` | 运行状态与指标 | 否 |

路径与大小：导出文件须在 `~/.butler/exports/` 或 `<项目>/.butler/exports/`，默认 ≤5MB（`BUTLER_EXPORT_SEND_WECHAT_MAX_BYTES`）。

---

## 异步委派（`delegate_task` + `delegate_categories.yaml`）

### 何时后台执行

同时满足：

1. `BUTLER_DELEGATE_ASYNC=1`（默认开）
2. **顶层** gateway turn（`depth=0`），且有 outbound bridge（微信长连接）
3. 类别未显式 `background: false`

内置 [`butler/delegate/delegate_categories.yaml`](../../butler/delegate/delegate_categories.yaml)：

| 类别 | `background` | 含义 |
|------|--------------|------|
| `quick` | `true` | 浅任务，后台 + 完成推送 |
| `deep` | `true` | 标准实现，后台 + 完成推送 |
| `ultrabrain` | `false` | 分析类，**同步**跑完再回复 |

覆盖：复制到 `~/.butler/delegate_categories.yaml` 按需改。

### 何时仍同步

- CLI / 无 bridge 的会话
- 子代理内 `delegate_task`（`depth>0`）
- `background: false` 的类别
- `BUTLER_DELEGATE_ASYNC=0`

### 完成通知

- 后台线程结束后经 `DelegatePushTarget` 推送（不依赖已 `end_turn` 的 bridge）
- `BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY` / `BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE` 控制频率

父会话 **Ctrl+C / 中断** 会取消登记中的子委派（`delegate_registry`）。

---

## 上下文与 Transcript

| 能力 | 环境变量 / 命令 | 说明 |
|------|-----------------|------|
| Turn 压缩 + split turn | `BUTLER_COMPACTION_*` | 超 token 预算时摘要旧消息 |
| Overflow replay | `reactive_compact` | 溢出后重放裁剪消息 |
| 显式 compaction turn | `BUTLER_COMPACTION_EXPLICIT_TURN` | transcript 事件 `compaction_turn` |
| Pre/Post compact hooks | `hooks.yaml` | `PreCompact` / `PostCompact` |
| Transcript 导出 | `/导出` | `BUTLER_SESSION_TRANSCRIPT=1` |
| Transcript 回滚 | `/回滚` | `BUTLER_TRANSCRIPT_REVERT_KEEP_LINES` |
| Transcript user fork | `/fork-transcript` `/分叉` | `butler/core/transcript_fork.py` |
| Remote compact | `BUTLER_REMOTE_COMPACT=1` | 失败回退本地 auxiliary；见 [sprint-codex-c2-2026-05.md](./sprint-codex-c2-2026-05.md) |
| thread_item 出站 | 压缩完成 | `health.thread_items` / `outbound_events` `kind=thread_item` |
| 子会话 transcript | `child_session_key` | 委派独立 jsonl + 事件 |

---

## 权限与安全

| 能力 | 配置 |
|------|------|
| 一次 / 始终批准 | `/批准一次`、`/始终允许`；`BUTLER_PERMISSION_ONCE_TTL` |
| `external_directory` | `permissions.yaml` + `path_safety` |
| Doom loop | `BUTLER_DOOM_LOOP_MODE=block\|ask`；`ask` 走 Owner 批准 |
| Git worktree 工具 cwd | `BUTLER_PROJECT_WORKTREE=1` + `project.yaml` `worktree:` |

模板：[`docs/templates/permissions.yaml.example`](../templates/permissions.yaml.example)

---

## P2 工程化

| 能力 | 开关 |
|------|------|
| Todo priority + 子代理禁 todos | `BUTLER_SESSION_TODOS=1`；委派 deny `session_todos_write` |
| post-edit format | `BUTLER_POST_EDIT_FORMAT=1` |

---

## 验收清单（发版后 10 分钟）

1. Owner 发 `/导出` → 收到文字摘要 + `.md` 文件（或关闭 `BUTLER_EXPORT_SEND_WECHAT_FILE=0` 仅路径）
2. `delegate_task` + `category=quick` → 主 turn 先结束，稍后收到「委派完成」推送
3. `/回滚 20` → transcript 行数减少；下一轮对话不引用已删行
4. `/批准一次` 后重复工具不再弹 pending（同会话）
5. `pytest tests/test_transcript_export.py tests/test_async_delegate.py tests/test_p3_features.py -q`

---

## 相关文档

- 全量 env：[`config/reference.md`](../config/reference.md)
- 微信运维：[`wechat-gateway-ops.md`](./wechat-gateway-ops.md)
- 对比报告：[`plans/opencode-butler-comparison-report-2026-05.md`](../plans/comparisons/opencode-butler-comparison-report-2026-05.md)
