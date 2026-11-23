# 本地 Demo 控制台 + Playwright E2E — 任务

> **配套规格**：[`spec.md`](spec.md)
> **状态**：已交付（2026-11-23）

## 任务清单

### T1 — 装配暴露 `fetch`

- [x] [`apps/api/src/acceptance-app.ts`](../../../apps/api/src/acceptance-app.ts)：`buildHonoApp`
      返回 `fetch(req, env?)`，内部 `app.fetch(req, env)`；保留 `request`。
- [x] [`tests/acceptance/harness.ts`](../../../tests/acceptance/harness.ts)：`AcceptanceApp`
      增加 `fetch` 字段并透传。
- [x] 现有 acceptance 测试与 `scripts/demo.ts` 不回归（未改调用方；全量 vitest 通过）。

### T2 — demo server

- [x] 新建 `scripts/demo-server.ts`：`node:http` + 127.0.0.1，端口 `BUTLER_V5_DEMO_PORT`（默认 4520）。
- [x] 实现 `/`、`/health`、`/demo/api/chat`、`/demo/api/approvals`、
      `/demo/api/approvals/:stepId/approve|deny`、`/demo/api/reset`。
- [x] 写入 §3.2 fixtures；请求串行队列；body/消息长度限制；SIGINT/SIGTERM 清理。
- [x] HTML 控制台：消息区、待审批卡片、批准/拒绝、重置、中文错误提示、`data-testid`。
- [x] `package.json` 增加 `demo:web`。

### T3 — Playwright

- [x] 根 `devDependencies` 安装 `@playwright/test`（1.65.1）并更新 lockfile。
- [x] 新建 `playwright.config.ts`（testDir、baseURL、webServer、trace/screenshot）。
- [x] 新建 `tests/e2e-demo/console.spec.ts`，覆盖规格 §4 的 6 组用例。
- [x] `package.json` 增加 `test:e2e:demo`。
- [x] 本地跑通 `pnpm test:e2e:demo`（chromium 1255 已安装）。

### T4 — CI

- [x] `.github/workflows/ci.yml` 新增 `demo-e2e` job：install → playwright install → 跑 E2E → 失败上传报告。

### T5 — 文档

- [x] 新增 `docs/deployment/DEMO.md`。
- [x] 更新 `README.md` 文档导航。
- [x] 更新 `docs/TESTS.md`（新增 Playwright 层 + 日期）。
- [x] 更新 `docs/PROGRESS.md`、`docs/ROADMAP.md` §4。
- [x] 更新 `docs/ENV.md`（`BUTLER_V5_DEMO_PORT`）。
- [x] 更新 `docs/plans/README.md` 索引本 spec。

### T6 — 全量验证

- [x] `pnpm format` → `pnpm format:check`
- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] `pnpm test`（279 文件 / 2,423 通过 / 2 skipped）
- [x] `pnpm test:e2e:demo`（4 passed）
- [x] `pnpm demo:web` + `curl /health` 手动冒烟（200）
- [x] 汇报结果；**不自动提交**，等 owner 指令

## 完成定义

- 规格 §4 六条 E2E 用例全部通过；
- 现有 2,423+ vitest 用例全绿，typecheck/lint/format 无新增告警；
- 文档索引与 ENV 表已同步；
- 工作区仅包含本次相关改动（不夹带既有未跟踪产物）。

## 偏差记录

- 端口 env 采用 `BUTLER_V5_DEMO_PORT`（而非 spec 初稿的 `BUTLER_DEMO_PORT`），与
  `docs/ENV.md` 的 `BUTLER_V5_*` 单前缀约定保持一致。
