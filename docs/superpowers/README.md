# superpowers · 异构 Agent 协同实施库

> 单次设计的 spec + 配套实施计划（任务清单，TDD-ready）。
> 配合 [`../DOCUMENTATION.md`](../DOCUMENTATION.md) §4.4 / [`../../AGENTS.md`](../../AGENTS.md) 使用。

## 目录约定

| 子目录 | 命名 | 内容 |
|--------|------|------|
| `specs/` | `YYYY-MM-DD-<topic>-design.md` | 单次设计的 spec（决策、边界、验收、风险） |
| `plans/` | `YYYY-MM-DD-<topic>.md` | 实施计划（任务清单，TDD-ready，含 review checklist） |

文件名 `<topic>` 用 kebab-case 简短主题（如 `wfxm-blackboard`）。

## 当前内容

| 日期 | 主题 | spec | plan |
|------|------|------|------|
| 2026-07-13 | wfxm-blackboard | [`specs/2026-07-13-wfxm-blackboard-design.md`](specs/2026-07-13-wfxm-blackboard-design.md) | [`plans/2026-07-13-wfxm-blackboard.md`](plans/2026-07-13-wfxm-blackboard.md) |
| 2026-07-13 | p1-4-delegation-boundary | [`specs/2026-07-13-p1-4-delegation-boundary-design.md`](specs/2026-07-13-p1-4-delegation-boundary-design.md) | [`plans/2026-07-13-p1-4-delegation-boundary.md`](plans/2026-07-13-p1-4-delegation-boundary.md)（`eeaa4e01`）|

## 流程

新主题一般由 `superpowers:brainstorming` 引导产出 spec → `superpowers:writing-plans` 出 plan → `superpowers:executing-plans` 或 subagent-driven 执行。

## 相关

- 黑板入口：[`.blackboard/README.md`](../../.blackboard/README.md)
- 项目级黑板硬门：[`.claude/settings.json`](../../.claude/settings.json)（Stop hook）
- 文档分层：[`DOCUMENTATION.md`](../DOCUMENTATION.md) §4.4 superpowers/ 节
- 异构 Agent 引导：`AGENTS.md`「黑板（班次交接）」节