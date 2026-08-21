# WFXM BlackBoard State

_last_synced: 2026-08-21 09:47_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- Owner API 审批恢复走 `buildApiRunTrigger`；MCP manifest 可驱动默认连接（env 覆盖）。
- RunTrigger 已接入微信/Channel/API 审批；MCP manifest gate 已落地。

## 下一步

- v5 AI 守卫迁移（人工）；P4 单独立项；CLI RunTrigger；Capability Provider 注册表。

## 不要做

- 不要改受保护 v4 守卫文件；不要恢复 `_archive` 包到生产路径。

## 上一班

- Owner approval RunTrigger + MCP manifest 连接默认值；682 测试待 commit。
