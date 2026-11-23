# Phase 2 C1 — 自然语言提醒任务

> **配套规格**：[`spec.md`](spec.md)
> **状态**：已交付（2026-11-23）

## 任务清单

### T1 — 持久化

- [x] `packages/persistence/src/migrations/0017_reminders.sql`：新增 `reminders` 表与索引。
- [x] `packages/persistence/src/schema.ts`：`reminders` Drizzle 表定义。
- [x] `packages/persistence/src/reminder-store.ts`：`ReminderStore` 接口与 Drizzle 实现。
- [x] `packages/persistence/src/index.ts`：导出 store 与记录类型。
- [x] `run-migrations.ts` / migration registry 测试：登记 0017 并断言建表。
- [x] 单测：create / listActive / countActive / listDue / markFired / cancel。

### T2 — 时间解析

- [x] `apps/api/src/reminder-time.ts`：`parseReminderTime` 与 `formatReminderTime`。
- [x] 单测：`Asia/Shanghai`、显式偏移、非法日期、过去时间、daily/weekly 推进。

### T3 — 工具

- [x] `apps/api/src/reminder-tools.ts`：`create_reminder` / `list_reminders` /
      `cancel_reminder` 三个 `ToolDefinition`。
- [x] `tools.ts`：开关打开时注册工具与 LLM 描述；关闭时不可见。
- [x] `ButlerToolContext` 接入 `reminderStore`；从 `runButlerLoop` 注入。
- [x] 单测：创建成功、上限、过去时间、取消唯一/多条、列表为空、缺少微信身份。

### T4 — 到点 worker

- [x] `wechat-run-notify.ts` 抽出无 gate 的 `sendWechatText`，保留原 gate 包装。
- [x] `apps/api/src/reminder-worker.ts`：tick、发送、成功推进、失败重试、迟到审计。
- [x] `apps/api/src/reminder-config.ts`：开关 / tick / 上限解析。
- [x] `wiring.ts` + `bootstrap-wiring.ts`：注入 `reminderStore`。
- [x] `index.ts`：开关打开时启动 worker 并在退出时 stop。
- [x] owner 路由 `GET /v1/owner/reminders`。
- [x] 单测：到点发送、取消不发送、重复推进、发送失败保留、迟到审计。

### T5 — 文档

- [x] `docs/ENV.md`：补三个 `BUTLER_V5_REMINDERS_*`。
- [x] `docs/FEATURES.md`：提醒能力与边界。
- [x] `docs/PROGRESS.md`：记录本次交付。
- [x] `docs/plans/README.md`：索引本 spec。

### T6 — 验证

- [x] `pnpm format` → `pnpm format:check`
- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] `pnpm test`
- [x] 汇报结果，**不自动提交**

## 完成定义

- 规格 §4 七条判据有对应自动化用例；
- 默认关闭时既有 2,423+ 用例零回归；
- 关闭开关后无新增 worker / 工具可见性变化。
