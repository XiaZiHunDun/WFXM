# WFXM BlackBoard State

_last_synced: 2026-08-24 20:32_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md_
_commit: c6085d47_

## 主线

D1 审计 P0 **#1+#2 Done**：Todoist spec 入仓 + audit 路径迁 `~/.config/butler-v5/`。见 [`v5-d1-butler-home-audit-2026-08-24.md`](docs/plans/active/v5-d1-butler-home-audit-2026-08-24.md)。

## 下一步

- gateway restart + Todoist MCP smoke（lst-projects）
- **2026-09-11**：disable v4 systemd + tar 备份 `~/.butler`
- **2026-09-18**：分块删 v4 子树（§7）

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（备份前）

## 上一班

- D1 P0：todoist yml → `butler-v5/config/openapi/`；manifest 相对路径 + resolve；audit 默认 `~/.config/butler-v5/audit/subagent.jsonl`。
