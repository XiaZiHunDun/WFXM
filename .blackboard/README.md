# WFXM 黑板规约（必读）

> 异构 Agent（Claude Code、Cursor、Codex 等）的跨会话交接层。
> 任何 Agent 在 WFXM 上工作前，必须读 `state.md` + 本文件 + 最新一张班次卡。

## 谁读 / 谁写

| 组件 | 写者 | 读者 |
|------|------|------|
| `state.md` | 人工 + 班次结束聚合 | 所有 Agent（会话开始必读） |
| `shifts/<file>.md` | 当值 Agent（append-only） | 下一班 Agent |
| `log.md` | 当值 Agent（append-only 摘要） | 人 / Agent |
| `tasks/backlog.yaml` | 人工或 `butler blackboard sync-todos` | 所有 Agent |
| `tasks/claims/<id>.yaml` | 认领 Agent | 仲裁人 / 下一班 |

## Agent 枚举

`agent` 字段固定取值（新增值需在 README 末尾"新增 Agent"段追加）：

- `claude-code`
- `cursor`
- `codex`
- `opencode`
- `human`

## shift_id 命名

格式：`YYYY-MM-DD-<agent>-<NNN>`。序号 = 当日已有班次卡序号 + 1（按字典序扫 `shifts/`）。

## 班次流程（hard gate）

1. **会话开始**：
   - 读 `README.md`（本文件）
   - 读 `state.md`
   - 读 `shifts/` 最新 1-2 张卡
   - 若认领任务：编辑 `tasks/claims/<id>.yaml`（`status: claimed` → `in_progress`）
2. **会话中**：自由工作；可选 append `log.md`
3. **会话结束**（hard gate）：
   - 写 `shifts/<shift_id>.md`（YAML frontmatter + 详细叙述）
   - append `log.md` 一段 1-3 行摘要
   - 更新 claim（如有）
   - 更新 `tasks/backlog.yaml`（如有状态变化）
   - 可选：刷新 `state.md`
   - commit 这一组黑板变更

## Schema

见 `docs/superpowers/specs/2026-07-13-wfxm-blackboard-design.md` §4。
但仍以本 README 为 quick reference。

## 新增 Agent

若你的 Agent 不在 `## Agent 枚举` 列表中：
1. 在本段追加新值
2. 提交一个 PR 写明 "blackboard: add <agent-name> to agent enum"
3. PR 合并前先用 `agent: human` 占位写卡