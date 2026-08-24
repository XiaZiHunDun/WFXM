# WFXM BlackBoard State

_last_synced: 2026-08-24 09:32_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: (CLI fix pending push)_

## 主线

Project Knowledge K1 ✅ — commit `a90b175f` pushed，gateway 已重启，端到端验收通过。

## 验收

- `butler verify`：10 migrations 含 `0010_project_knowledge.sql`
- ingest：`POST /v1/owner/project-knowledge` WFXM MCP 笔记
- 微信 inbound：`recall_project_knowledge` ×2，命中 `[manual_note] MCP multi-server`

## 生产

- Gateway：`butler-v5-gateway.service` active（2026-08-24 restart）
- MCP：22 tools 不变
- PK inject 默认关（`BUTLER_V5_PROJECT_KNOWLEDGE=0`）

## 下一步

- 可选：生产开 `BUTLER_V5_PROJECT_KNOWLEDGE=1` 测工作集 prefix
- K1.1：sources.json watch / markitdown chain（按需）

## 不要做

- embedding / RAG Studio / 全盘索引

## 上一班

- PK K1 commit/push + gateway restart + E2E recall 验收；CLI add 字段修复。
