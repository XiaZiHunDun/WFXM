# WFXM BlackBoard State

_last_synced: 2026-08-24 10:54_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: (PK prod enable 待 commit)_

## 主线

Project Knowledge **K1 + K1.1 ✅** — 生产已开 inject + watch。

## 生产 PK

- `BUTLER_V5_PROJECT_KNOWLEDGE=1`（工作集 prefix 注入）
- `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH=1`（5min sync，首 tick skipped=7）
- sources：`config/project-knowledge-sources.json`（7 路径）
- 启用脚本：`butler-v5/scripts/cutover/enable-project-knowledge-prod.sh`

## 下一步

- P0 v5 AI guard 迁移（人工 checklist，非自动）
- 或按需加 `markitdownGlobs`  ingest PDF

## 不要做

- embedding / RAG Studio

## 上一班

- 生产启用 PK inject + watch；inject trace；gateway restart 验收。
