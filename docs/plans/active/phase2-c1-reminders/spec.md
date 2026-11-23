# Phase 2 C1 — 自然语言提醒（个人定时任务）规格

> **状态**：已交付（2026-11-23）
> **选点依据**：[`phase2-feature-deepening-2026-11-23.md`](../phase2-feature-deepening-2026-11-23.md) C1
> **默认开关**：`BUTLER_V5_REMINDERS_ENABLED=0`（关闭时工具不注册、worker 不启动）

## 1. 目标

让 owner 在微信里直接说「明天 9:30 提醒我交周报」，Butler 创建一条持久化提醒，
到点主动推送一条纯文本消息；支持查看与取消，进程重启后提醒仍然存在。

非目标：

- 不做 cron 表达式、不做任意重复规则（只支持 once / daily / weekly）
- 不做外呼、文件发送、工具调用或任何副作用（提醒只发送文本）
- 不复用 LLM 生成提醒内容，避免到点产生额外模型调用

## 2. 用户场景

| # | 说法 | 期望 |
|---|------|------|
| 1 | 「明天 9:30 提醒我交周报」 | 回复包含「已设置」+ 时间 + 内容 |
| 2 | 「每天早上 8 点提醒我看日程」 | 创建 daily 提醒 |
| 3 | 「每周一 9:00 提醒我发上周总结」 | 创建 weekly 提醒 |
| 4 | 「我有哪些提醒」 | 列出未完成提醒（时间 + 内容） |
| 5 | 「取消周三的提醒」 | 命中唯一一条则取消；多条则列出候选请 owner 指定 |
| 6 | 时间说不清（「晚点提醒我」） | 只追问一次，不猜时间 |

## 3. 设计

### 3.1 持久化

新增迁移 `0017_reminders.sql` 与 `reminders` 表：

| 列 | 类型 | 说明 |
|----|------|------|
| `reminder_id` | uuid PK | 提醒 id |
| `subject` | text | owner subject（创建者） |
| `wechat_user_id` | text | 推送接收人（创建时的 `ctx.wechatUserId`） |
| `conversation_id` | text | 创建来源会话 |
| `content` | text | 提醒正文（≤ 500 字） |
| `fire_at` | timestamptz | 下一次触发时间（UTC 存储） |
| `repeat` | text | `once` / `daily` / `weekly` |
| `status` | text | `active` / `done` / `cancelled` |
| `attempt_count` | integer | 已尝试推送次数 |
| `last_attempt_at` | timestamptz | 最近一次推送尝试 |
| `last_error` | text | 最近一次失败原因（脱敏后） |
| `fired_at` | timestamptz | 单次提醒完成时间 |
| `created_at` / `updated_at` | timestamptz | 审计时间 |

索引：`(status, fire_at)`、`(subject, status)`。

`ReminderStore`（`@butler/persistence`）：

- `create(input)`
- `listActiveBySubject(subject)`：按 `fire_at` 升序
- `countActiveBySubject(subject)`
- `listDue(nowMs, retryCooldownMs, limit)`：`active AND fire_at <= now` 且
  `last_attempt_at` 为空或早于冷却时间
- `markFired(id, nextFireAt, firedAt)`：once → `status=done`；daily/weekly → 推进
  `fire_at`、清空 `last_error`
- `markAttemptFailed(id, error, attemptedAt)`
- `cancel(id, subject)`：仅 `active` 可取消，返回是否成功

### 3.2 时间解析

固定 `Asia/Shanghai`（UTC+8，无夏令时）。新增 `apps/api/src/reminder-time.ts`：

- 接受 `YYYY-MM-DD HH:mm` / `YYYY-MM-DDTHH:mm[:ss]`（无时区 → 按 +08:00 解释）；
- 接受带 `Z` 或 `±hh:mm` 的完整 ISO；
- 返回 `{ ok, fireAtMs }` 或 `{ ok: false, reason }`；
- 过去时间：`once` 直接拒绝；`daily/weekly` 推进到下一个未来时点；
- 边界校验：月/日/时/分范围、`Date` 反向换算一致，防止 `2026-02-30` 被静默进位。

展示统一用 `Asia/Shanghai` 的 `YYYY-MM-DD HH:mm`，周几用中文（如「周一 09:00」）。

### 3.3 工具

新增三个低风险工具，注册受开关控制：

| 工具 | 参数 | 行为 |
|------|------|------|
| `create_reminder` | `content`（必填）、`fireAt`（必填）、`repeat`（可选，默认 `once`） | 校验时间与上限（默认 20 条/owner），写库，返回「已设置」+ 时间 + 内容 |
| `list_reminders` | 无 | 返回 active 列表；为空时明确回「当前没有提醒」 |
| `cancel_reminder` | `id` 或 `query`（二选一） | 唯一命中则取消；0 条回未找到；多条回候选列表 |

工具描述写入 `WEIBUTLER_LLM_TOOLS`，要求模型把自然语言时间转换成
`Asia/Shanghai` 的绝对时间；解析失败时由模型追问一次，而不是工具猜测。

工具只在 `BUTLER_V5_REMINDERS_ENABLED=1` 时出现于 `makeWeibutlerTools` 与
`llmToolsForButler`，关闭时对模型完全不可见。

### 3.4 到点推送

新增 `apps/api/src/reminder-worker.ts`：

- `startReminderWorkerIfEnabled({ wiring, env, send? })`，默认 tick 30s；
- 每个 tick：`listDue(now, 60_000, 20)` → 逐条发送；
- 发送走 `sendWechatText`（从 `wechat-run-notify.ts` 抽出的**无 gate** 底层发送），
  不要求 `BUTLER_V5_RUN_NOTIFY_ENABLED`；
- 消息格式：`【提醒】<content>`（重复提醒附加「每天/每周」说明）；
- 成功：once → `done`；daily/weekly → 推进下一次 `fire_at`；
- 失败：`markAttemptFailed`，下一 tick 在冷却（60s）后重试；
- 迟到超过 5 分钟：额外写审计 `reminder.missed`（仍然补发，正文标注原定时间）；
- 审计：`reminder.created` / `reminder.cancelled` / `reminder.fired` / `reminder.missed`，
  actor=`owner-direct`，detail 不含绝对路径与凭证。

### 3.5 装配与 owner 查询

- `Wiring` 增加 `reminderStore: ReminderStore | null`；`bootstrap-wiring` 创建。
- `apps/api/src/index.ts` 在开关打开时启动 worker，进程退出时 stop。
- owner 只读接口 `GET /v1/owner/reminders` 返回 active 列表（调试 / 验收用），
  与 worker 共用 store，不引入第二套查询。

## 4. 验收判据

1. 一句话创建后，回复包含「已设置」、时间、内容；
2. 到点 ±60s 内推送，内容与创建时一致；
3. 取消后不再推送；单次提醒触发后不再重复；
4. 重启进程（重建 app + 同一 PGlite 数据目录 / 同一 DB）后提醒仍在；
5. 每人超过上限时创建失败，原因可读；
6. 时间不明确或已过去时，工具返回可读原因，不静默改写；
7. `BUTLER_V5_REMINDERS_ENABLED=0` 时三个工具都不注册，worker 不启动。

## 5. 失败可见性

- 创建/取消失败：工具返回中文原因（如「提醒时间已过去，请给出未来时间」）；
- 推送失败：保留 active、记录 `last_error`，下个 tick 重试；
- 漏发（进程停机错过时间）：恢复后补发并写 `reminder.missed`；
- 缺少微信身份：创建时直接提示「当前渠道不支持提醒」，不写脏数据。

## 6. 回滚

- 关闭 `BUTLER_V5_REMINDERS_ENABLED` 即停止 worker 并隐藏工具；
- 已有 `reminders` 数据保留，重新开启后继续生效；
- 迁移为纯新增表，不影响既有表结构。

## 7. 验证命令

```bash
pnpm --filter @butler/persistence test
pnpm --filter @butler/api test
pnpm typecheck && pnpm lint && pnpm test
```

重点用例：时间解析（时区/非法日期/过去时间）、上限、取消、重复推进、
重启持久化、发送失败重试、开关关闭时不注册。
