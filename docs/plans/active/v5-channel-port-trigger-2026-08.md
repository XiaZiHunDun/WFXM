# Butler v5 — Channel 接生产 trigger-day ADR (2026-08)

> **状态**：ADR draft，待 operator review
> **目的**：把 "Slack / Telegram 真接生产" 这个决定点从隐含决策（每次重讨论）固化为单一权威流程：触发信号 / 完成门槛 / 撤销路径 / Channel Port 升降边界
> **驱动**：DESIGN §7.1（Channel 标"⚪ 隐性承载 conditions-admit"）+ §18（"第二 Channel：微信被证明是场景瓶颈"列为延后项）+ 单 Owner 产品定位 + handoff 纪律（DESIGN §19 + `feedback-handoff-discipline`）
> **范围**（一句）：Slack 与 Telegram 任一被 Owner 自报触发后，按本 ADR §5 最小门槛接生产；Channel Port 维持隐性承载不升 first-class

## 1. 背景

DESIGN §7.1 把 Channel 标为唯一"conditions-admit"状态的 Port（6 个已物化 Port 之外的唯一隐性 Port）。当前事实：

- `butler-v5/packages/adapters/src/wechat/` 是**唯一**实装的出站 channel adapter
- `packages/adapters/src/{slack,telegram}/` 目录**不存在** —— §7.1 那条"`{wechat,slack,telegram}`"注释只是规划性预期
- 6 个已物化 Core Port（Clock / Credential Provider / Event Store / Outbox / Snapshot / Projection）均不在 §18 延后项中；Channel 是唯一一条带"等真实需求"前置的 Port

v5 目前**没有**"channel 选型 / channel portfolio 扩展 / channel 加挂"的标准流程 —— 每接一个新 channel 都会重新讨论 scope / bar / Port 升降。本 ADR 把这段固化。

## 2. Scope

### 2.1 In scope（本 ADR 锁四件事）

| # | 决策 | 备注 |
| --- | --- | --- |
| 1 | **Trigger 信号 = Owner 自报** | 控制面 / shift card / dialog 任一处一句话；无量化阈值、无 secondary review |
| 2 | **Per-channel 独立** | Slack 与 Telegram 是两条独立 ADR 事件；任一完成即闭环，不等另一 |
| 3 | **Production-ready bar = 最小完成** | adapter 实现 + 单测 + 入/出站跑通 + Owner 端到端一条真实对话 |
| 4 | **Channel Port 维持隐性** | 不升 first-class Core Port；不动 `packages/ports/src/index.ts` barrel；不动 port-catalog 升降流程 |

### 2.2 Out of scope（显式不做）

- Channel Port 升 first-class Core Port —— 另立 ADR
- Channel portfolio 状态机 / 选型流程 / 配置 schema —— YAGNI；真出现 multi-channel governance 需求时另立
- WeChat deprecation / 退场 / 替换 —— WeChat 仍唯一在生产 channel；Slack/Telegram 是叠加非替代
- 多 Channel 间消息去重 / Conversation 跨 channel 关联 —— 真出现 Owner 实际场景再立 ADR
- Channel quota / rate limiting / 协议升级 —— 各 channel 协议级维护走该 channel adapter 的 PR，不经本 ADR
- Owner 自报以外的 secondary review / Operator 角色引入 —— 产品定位变化时另立 ADR
- Production-grade 加固（5 gate 全 0 / N 天并行 / shadow 期）—— 显式不做；未来需求再立 ADR
- Channel 抽象抽取（共用代码 / base class / 共享协议层）—— §7.1 + §18 "不预先为架构完整造抽象"；WeChat 是唯一参照，多 channel 共性需待第二个 channel 落地后才能抽象

### 2.3 Hard boundaries

- 不为 Slack/Telegram 预建架构抽象 / 不加 channel-portfolio 状态机
- 不引入 channel 配置文件 schema（Owner 自报本身即权威，不需 metadata）
- 不为这个 ADR 写测试或验证脚本（ADR 的 verification 是事件性 + 归档性，见 §7）
- 不破坏现有 5 gate（typecheck / lint / test / test:archived / test:prod）；新增 channel 单测并入 production 测试集，不进 archived
- 不升 Channel 为 first-class Port 后才能触发此 ADR（Channel 仍标隐性承载即可触发）

## 3. Trigger mechanism（owner 自报落地）

**Owner 怎么表达**
- 在 `state.md` 当前班次段、shift card、或 Owner 控制面 / dialog 任一处写一句话：`channel:request-integration slack`（或 `telegram`），附日期
- 表达形态不限（口语"想接 Slack"亦可），由下一个会话的接班者归一化为上述形式

**怎么被记录**
- 写入当前 shift card 的"下一步 / Owner intent"段（**不写 state.md 顶部**，避免机械刷日期；与 `feedback-doc-date-staleness` 一致）
- 记录字段最小：channel 名 + 日期 + Owner 原话（一句话）+ 当前 ADR ID（本 ADR）
- 触发后该 channel 名进入"已触发但未完成"清单，挂在本 ADR §7 完成记录段

**触发的产出**
- 本 ADR §6 增一行 `<channel-name>: triggered YYYY-MM-DD, status: in-progress`
- 不开新 artifact / 不开新 code path / 不改 port-catalog
- 下一班次接班时读到这行即可知道哪个 channel 已触发

**触发可撤销**
- Owner 写 `channel:revoke-integration slack` 同位
- 接班者从"已触发但未完成"清单移除该 channel 名
- 撤销不写本 ADR §5 consequences 段；撤销时若已完成，记录进 §7 完成记录段的"备注"列

## 4. Production-ready bar（最小完成四门槛，per-channel）

1. **Adapter 实现**
   - 在 `butler-v5/packages/adapters/src/{slack,telegram}/` 建目录
   - 实现入站 Trigger adapter + 出站 Outbox adapter
   - 协议级认证 + 消息解析 + 回复地址构造（与 WeChat adapter 同形，不抽公共抽象）
2. **单测覆盖**
   - 入站：合法消息 / 非法消息 / 重复消息（idempotency）/ 附件
   - 出站：文本 / 富媒体 / 失败重试（走现有 Outbox 重试机制）
   - 错误路径：协议错误 / token 失效 / 网络超时
3. **入/出站能跑通**
   - 测试环境跑一次端到端：模拟 Slack inbound → Run Engine → Slack outbound
   - Outbox 项正确写入、Outbox worker 能正确发送（复用 R12 已上 Outbox 实现）
4. **Owner 端到端走通一条真实对话**
   - Owner 在真实 Slack workspace 发一条消息 → Butler 通过 Slack 回一条
   - Run trace 完整（conversation / run / step / outbox 全有）
   - **本条是 ADR 完成的最关键证据；缺这条不记完成**

## 5. Consequences

**Positive**
- Slack/Telegram 接生产有明确单一路径，不再每次重新讨论 scope / bar / Port 升降
- Owner 自报即权威，与 v5 "单 Owner / 单信任域" 产品定位一致
- Channel 维持隐性承载，**不增加架构抽象**，符合 DESIGN §7.1 + §18 YAGNI 原则
- Trigger 记录复用 shift card，与 v5 现有 handoff 纪律同载体（DESIGN §19 + `feedback-handoff-discipline`）
- Per-channel 独立：Owner 可分批引入（先 Slack 验证流程，再决定 Telegram 是否需要）

**Negative / Risks**
- Owner 自报无 secondary review —— 单 Owner 系统下可接受（不存在"Owner 误触发"语义），但写明：未来若引入 shared Owner 或 Operator 角色，此 ADR 需重审
- 最小完成门槛低（无 5 gate / 无 N 天并行 / 无 shadow 期）—— 可能未来需补 production-grade 加固（**显式记录为后续 ADR 候选**）
- Trigger 记录分散在 shift cards，没有正式事件日志 —— 可接受：v5 handoff 纪律本就不引入二级 artifact
- 多次触发-撤销同 channel 时 shift card 有噪声 —— 可接受：每条带 timestamp 即可定位

**Neutral / 待观察**
- WeChat 与 Slack/Telegram 并行运行时 Outbox worker 负载涨 2-3x —— 现有 Outbox 已能扛（无需动作），但若 Owner 实际场景出现并发瓶颈，另立 ADR
- 多 Channel 并行引入新场景：同 Conversation 在 Slack 与 WeChat 来回如何去重 / 关联 —— **不在本 ADR 范围**，出现再立 ADR

## 6. Verification

本 ADR 的 verification 是事件性 + 归档性，不是测试性：

**ADR 落盘**
- 本 ADR 写入 `docs/plans/active/v5-channel-port-trigger-2026-08.md`，commit 推 origin main
- 关联文档（port-catalog.md / DESIGN §7.1）**不动**（Channel 仍标隐性承载；触发完成不升 Port）

**Trigger 机制可工作**
- 下一个会话接班者在 shift card / state.md 读到 `channel:request-integration slack` 一行
- 接班者知道：① 该 channel 已触发 ② 按本 ADR §4 完成门槛执行 ③ 完成后在本 ADR §7 完成记录段填一行

**完成归档**
- 每完成一个 channel，本 ADR §7 完成记录段增一条：`<channel-name>: completed YYYY-MM-DD, 证据=<commit-sha 或 Run-id>`
- "已完成 channel" 清单随每次 commit 累积

**5 gate 不退化**
- Slack/Telegram 接生产后，`CI= pnpm typecheck && CI= pnpm lint && CI= pnpm test && CI= pnpm test:archived` 仍全绿
- 新增 Slack/Telegram 单测并入 production 测试集（不进 archived），production 计数 `1008 pass` 涨
- Archived 计数**不涨**（archived 是历史债保护袋，不接新代码）

## 7. 完成记录（per-channel）

| Channel | 触发日期 | 状态 | 完成日期 | 证据（commit / Run-id） | 备注 |
| --- | --- | --- | --- | --- | --- |
| (示例行) | | | | | 表头示例；真实触发后由接班者填 |

## 8. 不要做（重申）

- **不要**碰 `.claude/settings.json` / `.cursorrules` / `AGENTS.md`（除 `[MANUAL-OVERRIDE]` operator 流程）
- **不要**为接 Slack/Telegram 升 Channel Port 为 first-class —— 另立 ADR
- **不要**复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 测试守这条）
- **不要**为生产代码 import `r2-shim` 任何内容
- **不要**改 pre-commit hook；commit 用 `--no-verify`（R9.5 / R7.5 protocol）

## 9. 依赖与关系

- **DESIGN §7.1**：Channel 显式标"⚪ 隐性承载（conditions-admit）"—— 本 ADR 是该状态的运行规则
- **DESIGN §18**：本 ADR 是"第二 Channel"延后项的 trigger 定义
- **`feedback-handoff-discipline`**：trigger 复用 shift card；不写满 handoff 仪式
- **`feedback-doc-date-staleness`**：state.md 顶部不机械刷日期
- **handoff `2026-08-28-r11-r12-handoff.md`**：本 ADR 是该卡"下一步候选 #1"的兑现
- **后续 ADR 候选**（按需启动，不预设优先级）：
  - Channel Port 升 first-class（多个 channel 接生产后抽象需求真出现时）
  - Channel quota / rate limiting（Owner 实际场景出现瓶颈时）
  - Multi-channel 去重 / 跨 channel Conversation（多 channel 并行场景真出现时）
  - Production-grade 加固（5 gate / shadow 期等真需求出现时）

---

> 写于 2026-08-28；与 R11 + R12 闭环后班次对齐；harness: brainstorming skill