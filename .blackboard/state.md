# WFXM BlackBoard State

_last_synced: 2026-08-24 12:05_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: (PK wechat smoke 待 commit)_

## 主线

Project Knowledge **K1 + K1.1 + 微信验收 ✅** — inject（0 toolCalls → Accepted）+ recall 工具链 smoke PASS。

## 生产 PK

- `BUTLER_V5_PROJECT_KNOWLEDGE=1` + `WATCH=1`
- sources：**10 路径**（+ `butler-v5/AGENTS.md`、`v5-engineering-handoff`）
- 条目：**14**（sync scanned=10, created=2）
- smoke：`scripts/cutover/smoke-project-knowledge.mjs` PASS

## 下一步

- P0 v5 AI guard 迁移（人工 checklist，非自动）

## 不要做

- embedding / RAG Studio

## 上一班

- 微信 PK inject/recall 验收；扩 sources；单测 + smoke 脚本。
