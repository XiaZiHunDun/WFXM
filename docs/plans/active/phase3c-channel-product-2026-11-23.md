# Phase 3c — 渠道层与产品能力打磨方案（2026-11-23）

> **状态**：体检完成；C1–C6 已交付（C3 为边界决策，暂不切换） | **前置**：任务层 B1–B10、管家层 B11–B16 已交付
> **范围**：`apps/api` 渠道入口与出站、`packages/adapters` 的 wechat/slack、`packages/runtime` 管家工具与规则、微信命令入口
> **方法**：静态阅读 + 既有测试比对，只记录有代码证据的问题；未核实项标「待验证」

---

## 1. 现状：两条入站管线并存

| 维度 | 旧 RunEngine 管线 | 新 ButlerRuntime 管线 |
|------|------------------|----------------------|
| 入口 | `/v1/wechat/inbound`、`/v1/channel/inbound`、Slack events、Telegram webhook | `/v1/wechat/butler/inbound` |
| 命令面 | `/最近` `/记忆` `/待办` `/撤销` `/重试` `/诊断` `/确认记忆` `/记住` `/记忆候选` `/audit` 等 | `/help` `/status` `/tasks` `/new` 确认/拒绝 |
| 模型工具 | 工作区工具与委派（read/write/run/…） | `start_task` / `list_tasks` / `task_status` |
| 出站 | 微信 JSON 出口 `finalizeReply`；Slack/Telegram 直接发送并截断 | `finalizeReply` + `splitForWechat` 分条 |

证据：路由注册 [routes.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes.ts#L89-L96)、旧命令入口 [wechat-inbound-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-inbound-commands.ts#L21-L65)、新管家工具 [butler-runtime.ts](file:///home/ailearn/projects/WFXM/packages/runtime/src/butler/butler-runtime.ts#L655-L686)、渠道入站 [channel-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/channel-inbound.ts#L76-L84)。

生产微信网关默认仍指向旧入口（`V5_INBOUND_URL` 默认 `/v1/wechat/inbound`，见 [.env.example](file:///home/ailearn/projects/WFXM/.env.example#L254)）；新管家入口目前是并行可选面，尚未 cutover。

---

## 2. 问题清单

### 渠道层

| ID | 严重度 | 症状 | 证据 | 现有测试 | 用户影响 |
|----|--------|------|------|----------|----------|
| CH-01 | 中 | Slack/Telegram 出站绕过 `finalizeReply`，markdown、内部术语、原始工具名与绝对路径可能直接露出（B16 只保护了微信出口） | [slack-events.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes/slack-events.ts#L91-L96)、[telegram-webhook.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes/telegram-webhook.ts#L81-L85)、对照 [butler-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/butler-inbound.ts#L102) | 有各自单测，无“出站已收口”断言 | 其他渠道回复风格与微信不一致，可能泄漏内部信息 |
| CH-02 | 高 | Slack/Telegram 长回复静默截断到 3900 字符，尾部直接丢弃；微信走 1800 分条，不丢内容 | [channel-outbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/channel-outbound.ts#L25-L39)、[slack-outbound.ts](file:///home/ailearn/projects/WFXM/packages/adapters/src/slack/slack-outbound.ts#L23-L38) | `channel-outbound.test.ts`、`slack-outbound.test.ts` 只验证截断 | 长结果（任务汇总、排查步骤）后半段永久丢失 |
| CH-03 | 中 | 新管家只挂微信 JSON 入口；Slack/Telegram/generic channel 全走旧引擎，同一产品在不同渠道能力不同 | [routes/butler.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes/butler.ts#L94-L96)、[channel-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/channel-inbound.ts#L76-L84) | 两条管线各自有测试，无跨渠道一致性测试 | owner 在 Slack 与微信得到不同命令与工具行为 |
| CH-04 | 中 | generic channel 未带 `messageId` 时，`idempotencyKey` 用当次 `turnId`，重复投递会重新执行；Slack/Telegram 有 messageId 可重放 | [normalize-inbound.ts](file:///home/ailearn/projects/WFXM/packages/runtime/src/intake/normalize-inbound.ts#L141-L152)、[telegram-webhook.ts](file:///home/ailearn/projects/WFXM/apps/api/src/routes/telegram-webhook.ts#L48-L55) | Telegram 去重有测试；generic 无 messageId 无测试 | 网关重试时重复建任务/重复调用工具 |
| CH-05 | 中 | 分段发送中途失败无补偿，用户只收到前半截；结果仅返回 `sent:false` | [butler-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/butler-inbound.ts#L97-L115) | 有“发送失败不丢 turn 结果”用例，无部分失败用例 | 长回复半截、用户不知道后面还有内容 |
| CH-06 | 中 | 审批主动推送 helper 未接生产，只在测试里被调用；detached 任务暂停/完成时不会主动通知 | [butler-inbound.ts](file:///home/ailearn/projects/WFXM/apps/api/src/butler-inbound.ts#L63-L76)（全仓仅测试引用） | `notifyApprovalIfPaused` 单测 | 开启 detached 后用户必须自己轮询 `/status` |
| CH-07 | 低 | `ChannelPort` 契约未定义空文本、超长、超时语义；微信实现不校验，Slack/Telegram 各自定义 | [channel.ts](file:///home/ailearn/projects/WFXM/packages/ports/src/core/channel.ts#L23-L34)、[wechat/channel-port.ts](file:///home/ailearn/projects/WFXM/packages/adapters/src/wechat/channel-port.ts#L17-L34) | 各实现单测 | 新增渠道时容易再引入一套截断规则 |

### 产品能力

| ID | 严重度 | 症状 | 证据 | 现有测试 | 用户影响 |
|----|--------|------|------|----------|----------|
| PC-01 | 高 | 管家路径没有显式记忆写入：“记住：X”只有旧微信入口会落库，管家模型只能口头答应 | [butler-runtime.ts](file:///home/ailearn/projects/WFXM/packages/runtime/src/butler/butler-runtime.ts#L655-L686)、[wechat-memory-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-memory-commands.ts#L163-L211) | 旧入口 `wechat-commands.test.ts`；管家无 | “已记住”但下次不记得，信任受损（与 L4-4 同类） |
| PC-02 | 中 | 项目切换只在旧微信路径；管家 `projectId` 由请求体/env 固定，用户无法在会话里切项目 | [wechat-project-surface.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-project-surface.ts#L1-L15)、[butler.ts routes](file:///home/ailearn/projects/WFXM/apps/api/src/routes/butler.ts#L124-L130) | `project-state.test.ts` 等只覆盖旧路径 | 多项目 owner 在管家路径无法选择项目 |
| PC-03 | 中 | 撤销、重试、诊断、质量门、子代理只在旧微信入口；管家路径不可达，能力边界未文档化 | [wechat-inbound-commands.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-inbound-commands.ts#L21-L65)、[wechat-undo-command.ts](file:///home/ailearn/projects/WFXM/apps/api/src/wechat-undo-command.ts#L1-L16) | 旧路径有测试 | 用户按旧习惯发 `/撤销` 时，管家可能答非所问 |
| PC-04 | 中 | 产品能力清单描述旧引擎入口，未标注管家路径差异，文档承诺与当前入口漂移 | [FEATURES.md](file:///home/ailearn/projects/WFXM/docs/FEATURES.md#L26-L41) | — | Owner/贡献者误判“已有能力”在哪个入口生效 |

---

## 3. 建议批次

| 批次 | 主题 | 功能打磨 | 关键测评点（只测外部契约） | 状态 |
|------|------|----------|---------------------------|------|
| C1 | 出站一致性与分段 | Slack/Telegram 出站先过 `finalizeReply`，再按渠道上限分条发送；移除静默截断；部分失败可感知 | 长回复在 Slack/Telegram 分多条、每段不超限、无 markdown/绝对路径；第二段失败返回 `sent:false` 且原因可读 | ✅ 已交付 |
| C2 | 入站重复投递 | generic channel 无 `messageId` 时给出稳定去重键或显式拒绝重复；Slack/Telegram 重放语义统一 | 同一 messageId 重投只执行一次、回复一致；无 messageId 的行为有明确契约 | ✅ 已交付 |
| C3 | 渠道-管家入口归一 | 决策项：Slack/Telegram 是否切到 ButlerRuntime；先做可回滚开关与能力对照，不做大爆炸切换 | 开关关闭行为不变；开启后 `/help`、`/new`、审批在各渠道可用；失败可回退 | ✅ 决策：暂不切换（边界见 §6） |
| C4 | 任务主动通知 | 将 `notifyApprovalIfPaused` 与任务完成通知接到 detached 任务，经 ChannelPort 推送 | 任务暂停/完成各主动推送一次；不重复刷屏；推送失败只记日志不影响任务 | ✅ 已交付 |
| C5 | 显式记忆写入 | 管家路径支持“记住：X”（规则或工具）落库并回执；与旧入口一致的去重与失败提示 | “记住 X”后落库并回执；相似记忆提示重复；存储缺失返回可读失败 | ✅ 已交付 |
| C6 | 项目切换与能力边界 | 管家路径支持切项目；同时把两条管线的能力差异写进清单，避免承诺漂移 | 切换后 `/new` 使用新项目；未知项目可读拒绝；文档标注入口 | ✅ 已交付 |

---

## 4. 测评原则

- 硬关键点用确定性 vitest：去重、分段上限、部分失败、落库、项目隔离、推送一次。
- 软体验交给开放任务 + judge：措辞、追问风格、信息取舍。
- 明确放过：渠道适配器的内部重试次数、HTTP 头构造、日志字段、两条管线内部 trace 顺序。

---

## 5. 下一步

1. 确认批次顺序与 C3 的取舍（建议先 C1/C2/C4/C5，C3 单独决策，C6 跟随）。
2. C1 先做：它同时消除 CH-01/CH-02，改动集中在出站出口，可逆且能立即补上跨渠道体验。

---

## 6. 渠道-管家能力边界（C3 决策：暂不切换）

决策：生产继续以旧 RunEngine 为默认入口；ButlerRuntime 保持可选入口，本阶段不做默认 cutover。原因是管家路径虽已补齐任务相关能力，但质量门、子代理仍只在旧入口。

灰度开关（C3 清理交付）：`BUTLER_V5_<CHANNEL>_ENGINE`（如 `BUTLER_V5_SLACK_ENGINE`、`BUTLER_V5_TELEGRAM_ENGINE`）优先于 `BUTLER_V5_CHANNEL_ENGINE`；仅值 `butler` 生效，未设置或其它值保持旧入口。管家管线的项目由 `BUTLER_V5_CHANNEL_PROJECTS`（channelId → projectId 的 JSON）决定，缺省回退 `BUTLER_V5_DEFAULT_PROJECT_ID`，再回退 `wechat`。回退只需清空 `*_ENGINE`。

| 能力 | 旧入口 | 管家入口 |
|------|--------|----------|
| 任务创建 / 查看 / 审批 | 工具 + 命令 | `/new` `/tasks` `/status` 确认/拒绝 |
| 显式记忆 | `/记住` | `/remember`、`记住：X` |
| 项目切换 | `/切换` | `/project`、`切换项目 X` |
| 撤销 / 重试 / 诊断 | 有 | 有：`/undo`（边界说明）、`/retry`、`/diagnose` |
| 质量门 / 子代理 | 有 | 无（仍留在旧入口） |
| 工程执行（读写 / 命令 / 委派） | 模型工具 | 任务层 pi runner |

切换前置条件已满足：管家路径补齐 owner 依赖的撤销/重试/诊断能力；具备 per-channel 灰度开关与回滚；关键能力有外部契约测试。生产默认仍为 legacy，直到质量门/子代理迁移另有决策。

---

## 7. 交付记录（2026-11-23）

**C1 出站一致性与分段**

- Slack/Telegram 出站先 `finalizeReply` 再 `splitForWechat` 分条，移除 3900 静默截断（适配器裁剪保留为防御上限）。
- 媒体文本走同一收口；Telegram caption 按 1024 拆分，剩余文本继续分条。
- 分段失败返回「第 n/m 段」与原始原因，不再静默丢弃后半段。

**C2 入站重复投递**

- 无 `messageId` 时使用「渠道 + 会话 + 1 分钟窗口 + 内容指纹」生成幂等键；同窗口重投复用上次回复，跨窗口或不同内容正常执行。
- 微信与 generic channel 共用该策略，避免网关重试重复建任务。

**C4 任务主动通知**

- `PiTaskPortAdapter` 新增 detached-only `onSettled`；装配层由 `BUTLER_V5_DETACHED_TASKS` 开启。
- 路由维护 conversationId → 微信地址映射；暂停推审批通知，完成/失败推结果摘要；推送失败只记日志，不影响任务。
- `notifyApprovalIfPaused` 从「仅测试引用」变为真实可由 settle 事件驱动的路径。

**C5 显式记忆**

- 新增 `/remember <内容>`、`/记住 <内容>`、`记住：<内容>`，写入 `ButlerMemoryPort.rememberUserMemory` 并回执。
- 记忆端口未接入或写入失败时给可读提示；与 B14 自动投影共用同一事实源。

**C6 项目切换**

- `/project` 查看当前项目，`/project <id>` / `切换项目 <name>` 切换；别名解析由路由注入 `resolveWechatProjectAlias`。
- 选择写入 `ButlerSessionRecord.projectId` 并持久化，跨重启保留；任务列表/状态/创建与裸确认都以会话项目为准。
- 未知项目返回可读拒绝，且不改变当前项目。

**C3 遗留清理（2026-11-23）**

- 管家规则新增 `/retry [任务ID]`、`/diagnose`、`/undo`；`/diagnose` 不调模型，`/undo` 仅说明边界与手工回滚。
- `ButlerTaskPort.retry` 与 pi 适配器：failed / idle / closed 重跑，paused 无 pending 时恢复，paused 有 pending 时不自动批准。
- per-channel 灰度：`BUTLER_V5_<CHANNEL>_ENGINE` / `BUTLER_V5_CHANNEL_ENGINE`，默认 legacy；`BUTLER_V5_CHANNEL_PROJECTS` / `BUTLER_V5_DEFAULT_PROJECT_ID` 决定管家项目。
- Slack / Telegram / generic channel 在 butler 模式下共用 `createButlerRuntimeProvider`，通知按渠道经 ChannelPort 推送；旧入口代码路径未改。
- 新增契约测试：`butler-channel-cutover.test.ts`、channel-config 引擎/项目解析、任务端口重试与管家分支用例。

验证结果：

| 项 | 结果 |
|----|------|
| 定向测试（butler / 渠道 / 入站 / intake） | 全部通过 |
| `pnpm test` | 277 文件 / 2,381 通过 / 2 skipped |
| `pnpm typecheck` / `pnpm lint` | 全绿（0 warning） |
| `scripts/audit/test-internal-assertions.mjs` | 49 internal-only（2.4%，2,081 用例） |
