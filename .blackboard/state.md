# WFXM BlackBoard State

_last_synced: 2026-08-24 14:12_
_handoff: docs/plans/active/v5-project-knowledge-handoff-2026-08.md_
_commit: ef61a1fc_

## 主线

- **Done**：P0 `.cursorrules` v5 守卫收敛（已 push `ef61a1fc`）
- **Done**：PK sources 扩展（WFXM +5 文档；新增 `LingWen` 10 globs）；sync `scanned=25 created=15`

## 生产 PK

- env：`PROJECT_KNOWLEDGE=1` + `WATCH=1` + sources manifest
- gateway：healthz ok；manifest 已扩（需 restart 后 watch 读新 manifest，sync 已即时生效）
- WFXM ~19+ 条；LingWen 10 条（file_snapshot）

## 下一步

- **日历 D1**：2026-09-18 删 `~/.butler/`（距今约 25 天，Owner 再确认）
- `.claude/settings.json` v4 并存 — 待 v4 只读归档
- 真机微信 PK 复验（可选）
- 灵文微信 projectId 是否与 `LingWen` 对齐 — 使用前确认

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 前）

## 上一班

- push guard 收敛；扩 sources + 生产 sync；pnpm test 775 pass。
