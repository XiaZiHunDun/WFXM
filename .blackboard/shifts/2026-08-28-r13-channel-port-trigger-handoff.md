---
date: 2026-08-28
produced: [commit, doc]
---
# Butler v5 — R13 Channel Port Trigger ADR 闭环后的会话交接提示词

## 项目当前态（生产端）

- **HEAD**：origin/main = `2e420d8e`（R11+R12 闭环之上叠加 3 commits：`a740ecae` ADR → `62c2ae1d` 模板 → `2e420d8e` R13 state.md）
- **测试**：production `182 files / 1008 pass / 1 skip / 0 fail`；archived `18 files / 81 + 2 pre-existing run-loop rot`（R12 已知债，未变）
- **PRD §9**：R11+R12 已闭环 10/11（operator accept）；R13 是 handoff "下一步候选 #1" 的兑现 —— ADR 锁定 Slack/Telegram 接生产的触发条件，**未触发任何 channel**
- **Channel Port 状态**：仍 `⚪ 隐性承载（conditions-admit）`（DESIGN §7.1）；R13 显式不升 first-class

## 新会话必读（按顺序）

1. **本卡（`.blackboard/shifts/2026-08-28-r13-channel-port-trigger-handoff.md`）** ← 你正在读
2. **`.blackboard/state.md`** —— "**R13 Channel Port Trigger ADR 收口（2026-08-28）**" 段（在顶部 bulleted list，紧跟 `_handoff:` 行后）
3. **`docs/plans/active/v5-channel-port-trigger-2026-08.md`** —— R13 ADR（commit `a740ecae`）
4. **`docs/plans/templates/channel-integration-prd.md`** —— per-channel PRD 克隆模板（commit `62c2ae1d`）
5. **`.blackboard/shifts/2026-08-28-r11-r12-handoff.md`** —— R11+R12 上下文（HEAD 那时 = `1aef2e7d`）
6. **`butler-v5/DESIGN.md`** §7.1（Channel 隐性承载行）+ §18（第二 Channel 延后项）
7. **`docs/superpowers/plans/2026-08-28-wfxm-v5-channel-port-trigger-adr-implementation-plan.md`** —— R13 计划（已完成）

## 关键路径速查

| 用途 | 路径 |
| --- | --- |
| R13 ADR | `docs/plans/active/v5-channel-port-trigger-2026-08.md` |
| per-channel PRD 模板 | `docs/plans/templates/channel-integration-prd.md` |
| Channel adapter 目录（只 wechat 在） | `butler-v5/packages/adapters/src/wechat/` |
| DESIGN §7.1（Channel 行） | `butler-v5/DESIGN.md` |
| port-catalog.md（Channel 未变） | `butler-v5/packages/ports/port-catalog.md` |
| 现有 Outbox 实现（R12 已上） | `butler-v5/packages/ports/src/core/outbox.ts` |
| 现有 Core Port barrel | `butler-v5/packages/ports/src/index.ts`（thin barrel） |

## 下一步候选（user 给题再做，不要预设优先级）

1. **Owner 自报 Slack（或 Telegram）→ 启动 per-channel PRD**（克隆模板，把 `<CHANNEL_NAME>` 替为 slack 或 telegram，按 ADR §4 四门槛执行；触发记录写 shift card / state.md 一句话即可）
2. **Channel Port 升 first-class Core Port**（多个 channel 接生产后抽象需求真出现时；当前零抽象符合 §7.1 + §18 YAGNI）
3. **Model Port 立项**（多 Provider 协议/记账统一需求真出现时）
4. **archived rot 修复**（`_archive/packages/application/_archive/run-loop/run-loop.test.ts` Effect v3.x `Die`/`Fail` 断言或 mock 预期 stale）
5. **roadmap P5 段更新**（postgres 子项已 ✅，可改状态）
6. 新能力 / 修 bug

## 不要做（重申避免再撞）

- **不要**碰 `.claude/settings.json` / `.cursorrules` / `AGENTS.md`（除 `[MANUAL-OVERRIDE]` operator 流程）
- **不要**机械刷 state.md 顶部 `_last_synced` 日期；新班段写在顶部 `_handoff:` 行后（newest-first 风格），不在 `_last_synced` 行也不在末尾追加
- **不要**为 Slack/Telegram 升 Channel Port 为 first-class（另立 ADR；R13 §2.1 决策 4）
- **不要**复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 测试守这条）
- **不要**为生产代码 import `r2-shim` 任何内容
- **不要**改 pre-commit hook；commit 用 `--no-verify`（R9.5 / R7.5 / R11.1 protocol）
- **不要**为 Slack/Telegram 抽 channel 公共抽象（DESIGN §7.1 + §18 "不预先为架构完整造抽象"；WeChat 是唯一参照，多 channel 共性需待第二个 channel 落地后才能抽象）

## 我的失误（避免重蹈）

- **R13 plan 把 R13 state.md 入口写"append at END"**——实际 state.md bulleted list 是 **newest-first**（顶 P5/R11/R12 班段 → 底 P0-P4 老班段），R13 班段应在顶部 `_handoff:` 行后插入，**不是末尾追加**。**修法**：执行 Task 2 时已发现并纠正（Edit 替换 `_handoff:` 行 + 行末追加 R13 内容）；下次写此类班段位置前先 `head -10 state.md` 确认方向。
- **5 gate baseline 验证时 bash pipe `$?` 误读**——`CI= pnpm test:archived 2>&1 | tail -3 && echo "$?"` 中 `$?` 是 `tail` 的 exit，不是 `pnpm test:archived` 的 exit。**修法**：下次 archived 类门禁用 `${PIPESTATUS[0]}` 取首段 exit，或直接 `pnpm ... ; echo $?`。

## 时序与依赖

- R11 + R12 closure（9 commits, `8084fcc8` ... `27733cd7`）
- R13 Channel Port Trigger ADR（3 commits, `a740ecae` ... `2e420d8e`）
- 当前 5-gate：CI= pnpm typecheck && CI= pnpm lint && CI= pnpm test && CI= pnpm test:archived（archived 2 pre-existing 已知）

## Commit 链阅读路径（按发现顺序）

```
2e420d8e  docs(blackboard)   R13 班段 — channel-port-trigger ADR 收口记录
62c2ae1d  docs(plans)        per-channel integration PRD 模板
a740ecae  docs(plans)        channel-port-trigger ADR draft
1aef2e7d  docs(blackboard)   R11+R12 shift handoff card
27733cd7  docs(blackboard)   R12 closure — operator accepted
```

## 立刻能上手的最小动作

```bash
cd /home/ailearn/projects/WFXM
git pull                                                    # HEAD = 2e420d8e
git log --oneline -6                                        # 看 R13 链
CI= pnpm typecheck && CI= pnpm lint && CI= pnpm test && CI= pnpm test:archived  # 期望 1008/1/0
head -10 .blackboard/state.md                               # 看 R13 班段位置（顶部 _handoff: 行后）
```

如果 user 给题，按本卡 §"下一步候选" 各条核对 PRD / current file 再下手。
如果 user 没指题，等 user 报题目——别自动启动。