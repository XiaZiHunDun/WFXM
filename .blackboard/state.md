# WFXM BlackBoard State

_last_synced: 2026-08-21 09:35_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- RunTrigger 已接入微信/Channel 入站；MCP manifest 文件加载（`BUTLER_V5_MCP_MANIFEST_PATH`）已接入 bootstrap。
- application / infrastructure 已全部归档；Channel 富媒体、MCP session、Grant 动态 hosts 已交付。

## 下一步

- v5 AI 守卫迁移（人工 checklist）；P4 浏览器/Schedule/UI 单独立项。

## 不要做

- 不要改受保护 v4 守卫文件；不要恢复 `_archive` 包到生产路径。

## 上一班

- RunTrigger → RunEngine + MCP manifest 文件 gate；测试全绿待 commit。
