# WFXM BlackBoard State

_last_synced: 2026-08-20 16:20_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- Butler v5 是唯一活动产品；v4 已退役。
- 目标架构未提交：三模块五实体；长对话不变量已写入 DESIGN（Conversation 无界、Run 有界、同对话主 Run 串行、工作集有预算）。
- 工程交接已收成短 `state.md`。黑板不是产品运行时。
- 无进行中的编码任务。

## 下一步

- Owner 审阅后提交/推送目标架构与交接文档。
- 代码迁移另行立项：P0 schema 收口 → P1 Run / Policy / Grant → P2 沙箱。
- `.blackboard/README.md` 与 Stop hard gate 仍受保护，需人工改到新规约。
- D1：2026-09-18 前不删除 `~/.butler/`。

## 不要做

- 不把黑板迁进 v5 Run / Task。
- 不恢复 claims 或第二套 backlog。
- 不为百轮对话预建 ContextGraph / 向量库 / Session 聚合。

## 上一班

- 把长对话三条不变量写入 DESIGN §5.3 / §6.1 与产品边界。
