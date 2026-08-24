# WFXM BlackBoard State

_last_synced: 2026-08-24 11:56_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: c329105e_

## 主线

Project Knowledge **K1 + K1.1 ✅** — 生产 inject + watch + **PDF markitdownGlobs ✅**。

## 生产 PK

- `BUTLER_V5_PROJECT_KNOWLEDGE=1`（工作集 prefix 注入）
- `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH=1`（5min sync）
- sources：`config/project-knowledge-sources.json`（7 text globs + 2 markitdownGlobs）
- markitdown：`tests/fixtures/ext5/*.pdf`、`docs/**/*.pdf`
- 最新 sync：**scanned=8, created=1**（sample.pdf → ingested_document）
- 启用脚本：`butler-v5/scripts/cutover/enable-project-knowledge-prod.sh`

## 下一步

- P0 v5 AI guard 迁移（人工 checklist，非自动）

## 不要做

- embedding / RAG Studio

## 上一班

- PDF markitdownGlobs：scoped glob 修复 + sources 解析 + 生产 ingest sample.pdf 验收。
