# Phase 3c 遗留清理 Tasks

> 依赖：[spec.md](./spec.md) | 默认行为：legacy 不变，开关显式开启才走 butler

## T1 管家规则与帮助

- [x] `packages/runtime/src/butler/rule-router.ts`
  - `ButlerRuleAction` 增加 `retry` / `diagnose` / `undo`
  - `BUTLER_HELP_TEXT` 增加 `/retry`、`/diagnose`、`/undo`
  - `matchButlerRule` 增加显式命令匹配，位置在 `status/tasks/new` 之后、审批之前
- [x] `packages/runtime/src/butler/butler-runtime.test.ts` 增加规则匹配断言

## T2 运行时三分支

- [x] `packages/runtime/src/butler/butler-runtime.ts`
  - `handle()` 调 `applyRule` 传入 `session`
  - `retry`：6 类前置判断 + 调用 `tasks.retry` + 结果格式化 + 返回 `taskId`
  - `diagnose`：确定性文本，计数、待审批、最近任务 error 截断 120、记忆接入、提示
  - `undo`：固定边界文案
- [x] 测试：retry 无任务/无端口/继承最后任务/running/paused/成功；diagnose 正常与 list 抛错；undo 文案

## T3 任务端口重试

- [x] `packages/runtime/src/butler/pi-task-adapter.ts` 实现 `retry(taskId)`，按 spec §3.3 分支
- [x] `pi-task-adapter.test.ts`：failed 重跑、paused+pending 不批准、missing 返回 null

## T4 渠道开关与端口

- [x] `packages/ports/src/core/channel.ts`：`ChannelKind` 增加 `"generic"`
- [x] `apps/api/src/channel-config.ts`：`ChannelEngine`、`resolveChannelEngine`、`resolveChannelProjectId`
- [x] `apps/api/src/channel-config.test.ts`：引擎优先级、回退、项目解析、非法 JSON

## T5 运行时提供者

- [x] `apps/api/src/butler-projects.ts`：迁入 `parseProjectRoots`
- [x] `apps/api/src/routes/butler.ts`：import + re-export `parseProjectRoots`
- [x] `apps/api/src/butler-inbound.ts`：`createTaskSettledNotifier` 泛型化，`to` → `owner`
- [x] `apps/api/src/butler-inbound.test.ts`：同步 3 处 push 断言
- [x] `apps/api/src/butler-runtime-provider.ts`：provider、owner 映射、assembly 缓存、默认 push 分发

## T6 路由接线

- [x] `apps/api/src/routes/butler.ts`：接受/创建 provider，删除本地缓存与 owner map
- [x] `apps/api/src/channel-inbound.ts`：engine/butler/channel/ownerThreadTs、503、no-op、butler 分支返回
- [x] `apps/api/src/routes/slack-events.ts`：engine 判断、真实 ChannelPort、butler 模式不二次投递
- [x] `apps/api/src/routes/telegram-webhook.ts`：同上
- [x] `apps/api/src/routes/inbound.ts`：`registerInboundRoutes(app, wiring, butler?)`、generic engine 透传
- [x] `apps/api/src/routes.ts`：创建一次 provider 并传给四个路由

## T7 契约测试

- [x] `apps/api/src/butler-channel-cutover.test.ts`：butler `/help` 经 channel 投递、legacy 不变、provider 缺失 503
- [x] 测试设置并复原 `BUTLER_V5_CHANNEL_ALLOWLIST`

## T8 配置、场景与文档

- [x] `.env.example`：5 个新 env 注释与示例（默认 legacy）
- [x] `scripts/chat-scenarios/rules.json`：`/diagnose`、`/undo`、`/retry`
- [x] `docs/plans/active/phase3c-channel-product-2026-11-23.md` §6/§7
- [x] `docs/PROGRESS.md` 遗留清理小节
- [x] `docs/FEATURES.md` §1 与 butler 行

## T9 验证

- [x] `pnpm exec prettier --write` 改动文件
- [x] 定向 vitest：butler runtime、pi adapter、channel config、cutover
- [x] `pnpm test`
- [x] `pnpm typecheck && pnpm lint && pnpm format:check`
- [x] `pnpm verify:butler`
