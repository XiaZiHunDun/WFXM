# WFXM BlackBoard State

_last_synced: 2026-08-20 20:23_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- Butler v5 是唯一活动产品；v4 已退役。
- `main` 已含 P0–P2 全量迁移（fast-forward `9a967c0d`）；无需 PR 流程。
- Grant scope：审批时锁定 path + digest，执行时 mismatch 拒绝。

## 下一步

- Grant 网络 scope；MCP/多 Channel 条件准入。
- `.blackboard/README.md` 与 Stop hard gate 仍受保护，需人工改到新规约。
- D1：2026-09-18 前不删除 `~/.butler/`。

## 不要做

- 不把黑板迁进 v5 Run / Task。
- 不恢复 claims 或第二套 backlog。
- 不为百轮对话预建 ContextGraph / 向量库 / Session 聚合。

## 上一班

- 合并 feat/v5-target-p0-p2 → main；ScopedGrant path/digest 细粒度 + 600 测试全绿。
