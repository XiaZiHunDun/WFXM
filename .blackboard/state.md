# WFXM BlackBoard State

_last_synced: 2026-08-24 09:26_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: (K1 未 commit)_

## 主线

Project Knowledge K1 实施中 — Owner 决策 Accepted（A–F 全确认）。

## K1 进度

- ✅ domain + migration `0010` + store
- ✅ Owner API + `recall_project_knowledge` + opt-in inject
- ✅ CLI `butler project-knowledge`
- ⏳ `pnpm test` 全绿 → commit/push → gateway restart → 端到端验收

## 生产 MCP

- 22 tools；四 server Grant 均已验收
- `0010` migration 待 gateway restart 后 apply

## 下一步

1. 跑全量测试 + commit/push
2. restart gateway；ingest WFXM 笔记 → 微信 recall 验收

## 不要做

- embedding / RAG Studio / 全盘索引
- 从 v4 memory 机械移植
- 未验收前改生产 `BUTLER_V5_PROJECT_KNOWLEDGE=1`

## 上一班

- Owner 确认 PK 立项 A–F；K1 代码主体完成，补 CLI/测试/文档。
