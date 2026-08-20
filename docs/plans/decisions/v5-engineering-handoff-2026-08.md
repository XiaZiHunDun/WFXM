# Butler v5 工程交接（2026-08）

> **状态**：Accepted  
> **范围**：仓库内异构 Agent 的跨会话交接，不是产品运行时  
> **取代**：[`../../superpowers/specs/2026-07-13-wfxm-blackboard-design.md`](../../superpowers/specs/2026-07-13-wfxm-blackboard-design.md) 作为交接规约  
> **目标架构**：[`../../../butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md) §16  
> **受保护面**：`.blackboard/README.md` 与 `.claude/settings.json` 仍须人工改到本口径；在改完之前，以本文和 `AGENTS.md` 为准

---

## 1. 裁决

单 Owner 串行开发只需要一份当前快照。班次卡、摘要流、第二套 backlog 和认领锁超过真实并发。

交接层属于工程治理：

- 不进入产品数据库、Run 状态机或 API；
- 不映射为 Conversation、Task 或 Child Run；
- 不作为 Butler 的交付能力继续演进。

审计以 git 为准。聊天记录和 agent transcript 是细节，不是第二套账本。

---

## 2. 默认流程

**会话开始**：读 `.blackboard/state.md`。仅当快照过期或缺失时，再看最近一张 `shifts/` 卡。不要把 `MEMORY.md`、`backlog.yaml` 或 `log.md` 当当前待办。

**会话结束**：更新 `state.md`，使其不超过约 40 行，且只含：

1. 当前主线；
2. 下一步；
3. 不要做；
4. 上一班一句话。

短会话到此结束。不写班次卡，不追加 `log.md`，不改 `tasks/`，不强制提交黑板。

**长会话**（跨多个子系统、未完成的迁移、或下一班无法从 state 接上）可以额外写一张短卡到 `shifts/`。卡是可选附录，不是门禁。

---

## 3. 冻结

以下文件保留作历史，不再作为活动流程：

- `.blackboard/tasks/backlog.yaml` — v4 待办镜，产品待办看边界与路线图；
- `.blackboard/tasks/claims/` — 从未使用的防双抢；
- `.blackboard/log.md` — 与班次卡摘要重复；
- `butler/blackboard/` Python CLI — 可选工具，不是交接前置。

不要为校验器修路径、扩 schema 或把 Stop hard gate 当成产品功能。

---

## 4. 人工收口（受保护文件）

Owner 或人工应随后：

1. 把 `.blackboard/README.md` 改成指向本文的一页规约；
2. 去掉或关闭 `.claude/settings.json` 里 `BLACKBOARD_STRICT=1` 的 Stop hard gate，改为缺卡软提醒。

在此之前，Agent 仍须遵守本文，不得为了过旧 hook 而恢复五件套写卡。
