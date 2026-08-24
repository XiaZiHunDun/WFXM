# WFXM BlackBoard State

_last_synced: 2026-08-24 09:50_
_handoff: docs/plans/active/v5-project-knowledge-proposal-2026-08.md_
_commit: (K1.1 待 commit)_

## 主线

Project Knowledge **K1.1 ✅** — sources.json + watch worker + markitdown chain + Owner sync API。

## K1.1 交付

- `config/project-knowledge-sources.json`（WFXM 7 路径）
- `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH=1` opt-in 轮询
- `POST /v1/owner/project-knowledge/sync` + `butler project-knowledge sync`
- mtime/size 增量 skip；office/PDF → markitdown → document → PK

## 生产

- Gateway 待 restart 加载 K1.1
- PK inject 仍默认关

## 下一步

- restart gateway → `butler project-knowledge sync` 验收
- 可选开 `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH=1`

## 不要做

- embedding / RAG Studio / 全盘索引

## 上一班

- K1.1 实施：sources manifest、sync engine、watch worker、文档更新。
