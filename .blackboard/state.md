# WFXM BlackBoard State

_last_synced: 2026-08-25 09:45_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md_
_commit: 376412f0_

## 主线

D1 前置 **#1–#4 Done**：MCP spec + audit 路径迁移；v4 systemd 已停/disable；`~/.butler` 已 tar 备份。见 [`v5-d1-butler-home-audit-2026-08-24.md`](docs/plans/active/v5-d1-butler-home-audit-2026-08-24.md)。

## 下一步

- **2026-09-18 D1**：分块删 v4 子树（§7）；smoke 点验
- gateway **已 restart**（Todoist MCP 新 spec 路径已生效）
- （可选）导出 `tenants/default/memory/` 只读归档

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 日；备份在 `~/backup-butler-home-20260825.tgz`）

## 上一班

- stop/reset/disable v4 morning-brief（卡死 1 周）+ push-drain + b9；tar 88MB→12MB + sha256。
