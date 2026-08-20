# WFXM BlackBoard State

_last_synced: 2026-08-20 20:10_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- Butler v5 是唯一活动产品；v4 已退役。
- 分支 `feat/v5-target-p0-p2`：P1.0–P1.4 治理 + 微信内联审批已落地；P2 bubblewrap preflight 已加。
- 待开 PR 合并 `feat/v5-target-p0-p2` → `main`。

## 下一步

- 合并 PR；后续：Grant scope 细粒度、MCP/多 Channel 条件准入。
- `.blackboard/README.md` 与 Stop hard gate 仍受保护，需人工改到新规约。
- D1：2026-09-18 前不删除 `~/.butler/`。

## 不要做

- 不把黑板迁进 v5 Run / Task。
- 不恢复 claims 或第二套 backlog。
- 不为百轮对话预建 ContextGraph / 向量库 / Session 聚合。

## 上一班

- bubblewrap preflight（CLI + cutover 脚本 + systemd 注释 + 文档）；597 测试全绿。
