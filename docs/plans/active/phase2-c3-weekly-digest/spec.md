# Phase 2 C3 — 每周周报（主动摘要）规格

> **状态**：已交付（2026-11-23）
> **选点依据**：[`phase2-feature-deepening-2026-11-23.md`](../phase2-feature-deepening-2026-11-23.md) C3
> **默认开关**：`BUTLER_V5_WEEKLY_DIGEST_ENABLED=0`（关闭时 worker 不启动；手动 `/周报` 仍可用）

## 1. 目标

每周固定时间（默认周一 09:00，Asia/Shanghai）主动推送一条只读摘要，包含四项数字：
当周完成待办、当前 open 待办、当周失败 Run、当周审批请求。owner 也可随时发 `/周报`
获取同一份内容。

非目标：

- 不调用 LLM，不做自然语言总结；数字与现有 `/待办`、`/usage`、audit 查询口径一致。
- 不新增调度框架，不替代 schedule worker；周报是独立的 opt-in 推送。
- 不修改任务 / Run / 审批状态，只读。

## 2. 用户场景

| # | 场景 | 期望 |
|---|------|------|
| 1 | 周一 09:00 自动推送 | 收到「【周报】…」四项数字 |
| 2 | 微信发 `/周报` | 立即返回与自动推送结构一致的内容 |
| 3 | 一周没有任何完成 / 失败 / 审批，且无待办 | 自动推送静默（不打扰） |
| 4 | 查询失败 | 回复「周报生成失败：<原因>」并记 audit |
| 5 | 当天已推送后进程重启 | 不重复推送 |

## 3. 设计

### 3.1 统计口径

| 指标 | 来源 | 口径 |
|------|------|------|
| 完成 | `TaskStore.listBySubject({ subject })` | `status="done"` 且 `updatedAt` 落在最近 7 天 |
| 待办 | 同上 | 当前 `status="open"` 的全部任务（按 owner 维度，不按项目过滤） |
| 失败 | `getSharedLocalTracer().list()` | `kind="step"`、`name="run_failed"` 且 `createdAt` 落在最近 7 天（与 `/v1/owner/usage` 同源） |
| 审批 | `RuntimeStore.listRecentAuditEvents({ windowMs })` | `action="approval.requested"` 且 `createdAt` 落在最近 7 天 |

空周判定：四项全为 0 时 `hasData=false`，自动推送跳过；手动 `/周报` 返回
「过去 7 天没有可汇总的记录」。

### 3.2 渲染

纯函数，输入统计结果与时间窗，输出固定结构：

```
【周报】11-16 ~ 11-23
完成 3 项
待办 5 项
失败 1 次
审批 2 次
```

手动与自动共用同一 `renderWeeklyDigest`，不得出现第二套文案。

### 3.3 自动推送

新增 `apps/api/src/weekly-digest-worker.ts`：

- tick 默认 60s；仅当「上海时区星期 = 配置星期」且当前时间落在
  `[HH:mm, HH:mm + 10min)` 窗口内才尝试；
- 推送前查最近 7 天 audit：若同一 `dayKey` 已有 `weekly_digest.sent`，跳过
  （进程重启不重复）；
- 发送走无 gate 的 `sendWechatText`；
- 成功写 `weekly_digest.sent`（detail 含 dayKey + 四项数字）；
- 失败写 `weekly_digest.failed`（detail 含脱敏后的 reason），不重试到下周；
- 空周直接返回，不发消息。

配置：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_V5_WEEKLY_DIGEST_ENABLED` | `0` | 开关 |
| `BUTLER_V5_WEEKLY_DIGEST_TO` | — | 接收人 wechat user id；缺失时 worker 不启动 |
| `BUTLER_V5_WEEKLY_DIGEST_WEEKDAY` | `1` | 0=周日 … 6=周六 |
| `BUTLER_V5_WEEKLY_DIGEST_TIME` | `09:00` | Asia/Shanghai 的 `HH:mm` |
| `BUTLER_V5_WEEKLY_DIGEST_TICK_MS` | `60000` | 轮询间隔（5s–10min） |

### 3.4 手动命令

`/周报`（别名 `/weekly`）由 `tryWechatInboundCommand` 在 LLM 之前拦截，直接调用
`collectWeeklyDigest` + `renderWeeklyDigest`，不消耗模型调用。失败时回复
「周报生成失败：<原因>」并写 `weekly_digest.failed` audit。

### 3.5 装配

- worker 在 `apps/api/src/index.ts` 中按开关启动，退出时 stop；
- 不新增数据库表 / 迁移；
- owner 侧无新增 HTTP 接口（现有 `/v1/owner/usage`、`/v1/owner/tasks` 已覆盖明细）。

## 4. 验收判据

1. `/周报` 返回完成、待办、失败、审批四项数字；
2. 完成数来自 `TaskStore`，失败数来自 tracer `run_failed`，审批数来自 audit，
   与 `/v1/owner/usage`、`/v1/owner/tasks` 口径一致；
3. 空周时自动推送不发送；
4. `/周报` 与自动推送内容结构一致（同一渲染函数）；
5. 查询异常时返回「周报生成失败：<原因>」并写 audit；
6. 同一天重复 tick / 重启后不重复推送；
7. 开关关闭时 worker 不启动，`/周报` 仍可手动使用。

## 5. 失败可见性

- 查询异常：命令回复中文原因，audit 记 `weekly_digest.failed`；
- 推送失败：audit 记 `weekly_digest.failed`，不中断 worker，下周继续；
- 缺少接收人：启动时 warn，worker 不启动，不影响其他能力。

## 6. 回滚

- 关闭 `BUTLER_V5_WEEKLY_DIGEST_ENABLED` 即停止自动推送；
- 手动 `/周报` 为只读命令，可随时保留；
- 无 schema 变更，回滚不需要数据迁移。

## 7. 验证命令

```bash
pnpm --filter @butler/api test
pnpm typecheck && pnpm lint && pnpm test
```

重点用例：四项统计口径、空周、渲染结构、同日去重、失败审计、开关关闭。
