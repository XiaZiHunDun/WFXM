# WFXM BlackBoard State

_last_synced: 2026-08-21 09:51_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- CLI `butler run` + `createProductionCapabilityRegistry` 已落地；RunTrigger 四入口（微信/Channel/API/CLI）齐备。
- MCP manifest 可驱动连接；Owner 审批走 API RunTrigger。

## 下一步

- v5 AI 守卫迁移（人工）；P4 单独立项；MCP/Channel 注册为 extraProviders。

## 不要做

- 不要改受保护 v4 守卫文件；不要恢复 `_archive` 包到生产路径。

## 上一班

- CLI RunTrigger + Capability Provider registry；685 测试待 commit。
