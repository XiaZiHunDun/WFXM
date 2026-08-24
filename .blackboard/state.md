# WFXM BlackBoard State

_last_synced: 2026-08-24 16:25_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md_
_commit: 1bb64c93_

## 主线

§7 全收口；Claude Code Stop 改为 **state.md 软提醒**（去掉 `BLACKBOARD_STRICT=1`）。

## 下一步

- **D1 2026-09-18**：删 `~/.butler/` + 复核 v4-to-v5 migration（Owner 确认）
- v5 微信项目切换后：扩展 `INBOUND_MAP`（如 `灵文1号:LingWen`）
- `.blackboard/README.md` 改一页规约（受保护，Owner 人工可选）

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 前）

## 上一班

- settings.json 软提醒 + claude_session_end v5 校验；blackboard 测试更新。
