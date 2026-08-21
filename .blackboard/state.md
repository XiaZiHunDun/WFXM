# WFXM BlackBoard State

_last_synced: 2026-08-21 10:08_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- P3 接缝已齐：RunTrigger 四入口、MCP manifest/连接/extraProviders、Capability Provider 注册表。
- 生产路径：微信 + Channel（Slack/Telegram）+ Owner API/CLI + 审批/MCP opt-in。

## 下一步（按需）

- **v5 AI 守卫迁移**：人工 checklist，有空再做，不阻塞交付。
- **P4 候选**：Schedule/heartbeat、本地控制面 UI 等——有明确 Owner 场景再立项。

## 不要做

- **浏览器 / Playwright**：Owner 2026-08-21 明确不立项（见 `v5-product-boundaries` §7 Owner 立项记录）。
- 不要改受保护 v4 守卫文件；不要恢复 `_archive` 包到生产路径。
- Agent 不要把浏览器、RAG Studio、全量 MCP Marketplace 推入 backlog。

## 上一班

- ed1ca8cb MCP extraProviders；文档同步浏览器不立项 + AI 守卫排期说明。
