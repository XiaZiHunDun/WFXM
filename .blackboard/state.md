# WFXM BlackBoard State

_last_synced: 2026-08-24 14:18_
_handoff: docs/plans/active/v5-project-knowledge-handoff-2026-08.md_
_commit: (pending)_

## 主线

§7 **收口**：PK smoke PASS（WFXM + wechat→WFXM）；guard/unwired/D1 文档齐；settings.json 待 Owner。

## 生产 PK

- env：`PROJECT_KNOWLEDGE=1` + `WATCH=1` + `INBOUND_MAP=wechat:WFXM`（代码默认亦生效）
- WFXM 19 条；LingWen 10 条
- smoke：`node butler-v5/scripts/cutover/smoke-project-knowledge.mjs` PASS

## 下一步

- Owner：[`v5-claude-settings-owner-actions-2026-08.md`](docs/plans/active/v5-claude-settings-owner-actions-2026-08.md) 选 A/B
- **D1 2026-09-18**：删 `~/.butler/` + 复核 v4-to-v5 migration（Owner 确认）
- v5 微信项目切换接线后：扩展 `INBOUND_MAP` 支持灵文（如 `灵文1号:LingWen`）

## 不要做

- PK K2 / embedding / RAG Studio
- 删 `~/.butler/`（D1 前）
- 改 `.claude/settings.json`（AI block，Owner 人工）

## 上一班

- smoke + wechat→WFXM PK alias；§7 文档收口；pnpm test 待跑后 commit。
