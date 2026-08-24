# WFXM BlackBoard State

_last_synced: 2026-08-24 13:58_
_handoff: docs/plans/active/v5-project-knowledge-handoff-2026-08.md_
_commit: 472e92fe_

## 主线

Project Knowledge **Done**（K1 + K1.1 + 生产 + 微信 smoke）。下一班见交接文档。

## 生产 PK

- env：`PROJECT_KNOWLEDGE=1` + `WATCH=1` + sources manifest
- gateway：`butler-v5-gateway.service` active
- smoke：`butler-v5/scripts/cutover/smoke-project-knowledge.mjs`

## 下一步

- **P0** AI guard / `.cursorrules` 与 v5 守卫收敛（人工）
- 或 **按需** 扩 sources（灵文1号等）
- **日历** 2026-09-18：D1 删 `~/.butler/`（Owner 再确认）

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 前）

## 上一班

- 写 PK 全闭环交接文档；PK 线收口。
