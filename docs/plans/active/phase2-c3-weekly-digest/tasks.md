# Phase 2 C3 — 每周周报任务

> **配套规格**：[`spec.md`](spec.md)
> **状态**：已交付（2026-11-23）

## 任务清单

### T1 — 统计与渲染

- [x] `apps/api/src/weekly-digest.ts`：`collectWeeklyDigest`（tasks / runs / audit）
      与纯函数 `renderWeeklyDigest`。
- [x] 单测：四项口径、时间窗过滤、空周判定、渲染结构。

### T2 — 手动命令

- [x] `apps/api/src/wechat-weekly-digest-command.ts`：`/周报` 与 `/weekly`。
- [x] `wechat-inbound-commands.ts` 注册命令（LLM 之前拦截）。
- [x] 单测：正常输出、空周输出、查询失败文案 + audit。

### T3 — 自动推送

- [x] `apps/api/src/weekly-digest-config.ts`：开关 / 接收人 / 星期 / 时间 / tick。
- [x] `apps/api/src/weekly-digest-worker.ts`：时间窗判定、同日去重、发送、审计。
- [x] `index.ts`：开关打开时启动 worker 并在退出时 stop。
- [x] 单测：非触发日不发、空周不发、成功发送与审计、同日不重复、失败审计、开关关闭不启动。

### T4 — 文档

- [x] `docs/ENV.md`：补 `BUTLER_V5_WEEKLY_DIGEST_*`。
- [x] `docs/FEATURES.md`：周报能力与边界。
- [x] `docs/PROGRESS.md`：记录本次交付。
- [x] `docs/plans/README.md`：索引本 spec。

### T5 — 验证

- [x] `pnpm format` → `pnpm format:check`
- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] `pnpm test`
- [x] 汇报结果，**不自动提交**

## 完成定义

- 规格 §4 七条判据有对应自动化用例；
- 默认关闭时既有用例零回归；
- 手动 `/周报` 与自动推送共用同一渲染函数。
