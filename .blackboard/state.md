# WFXM BlackBoard State

_last_synced: 2026-08-24 14:10_
_handoff: docs/plans/active/v5-project-knowledge-handoff-2026-08.md_
_commit: 9e529a0b_

## 主线

Project Knowledge **Done**。本班：**P0 `.cursorrules` v5 守卫收敛**（v5 承重清单 + pnpm test + 陷阱段）。

## 生产 PK

- env：`PROJECT_KNOWLEDGE=1` + `WATCH=1` + sources manifest
- gateway：`butler-v5-gateway.service` active；healthz ok
- smoke：`butler-v5/scripts/cutover/smoke-project-knowledge.mjs`

## 下一步

- Owner 确认 `.cursorrules` diff 并 commit（含 `[MANUAL-OVERRIDE]` 若需）
- 或 **按需** 扩 sources（灵文1号等）
- **日历** 2026-09-18：D1 删 `~/.butler/`（Owner 再确认）
- `.claude/settings.json` v4 并存 — 待 v4 只读归档后收口

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 前）

## 上一班

- `.cursorrules` 对齐 v5-ai-guard 清单；PK 线已收口，不再开发。
