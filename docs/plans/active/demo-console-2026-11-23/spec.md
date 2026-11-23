# 本地 Demo 控制台 + Playwright E2E — 规格

> **状态**：已交付（2026-11-23）
> **日期**：2026-11-23
> **前置**：`c3241be9`（Phase 1 审批 TTL / 入站乱序）已推送
> **范围**：本地 + CI，不做公网实例、不接真实 LLM

## 1. 目标

给仓库补一个**可运行的浏览器 demo**：一条命令启动本地控制台，在网页里发消息、看到
Butler 回复、触发审批并批准/拒绝、一键重置；用 Playwright 覆盖这条交互链，并在 CI
中执行。

非目标：

- 不做生产 Web UI / 前端框架 / 构建链
- 不做公网部署、登录鉴权、多用户
- 不调用真实模型、不开启 MCP、不写宿主真实工作区

## 2. 现有可复用资产（已核实）

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| acceptance harness | [`tests/acceptance/harness.ts`](../../../tests/acceptance/harness.ts) | `makeAcceptanceApp()` 起生产 wiring + 内存 PGlite + 脚本化 fixture LLM |
| Hono 装配 | [`apps/api/src/acceptance-app.ts`](../../../apps/api/src/acceptance-app.ts) | 挂载入站路由 + owner 路由 |
| 入站接口 | `POST /v1/wechat/inbound`（需 `x-inbound-secret`） | demo server 代理 |
| 审批接口 | `GET /v1/owner/approvals`、`POST /v1/owner/approvals/:stepId/approve|deny` | demo server 代理 |
| 审批触发 | `write_file` 命中 `alwaysConfirm` → `WaitForApproval` | demo fixture 第二条 |
| CLI demo | [`scripts/demo.ts`](../../../scripts/demo.ts) | 保留不动，作为 zero-LLM REPL 入口 |

关键约束：`ownerAuthorized()` 依赖请求 socket 的 `remoteAddress`；vitest 之外的
`app.request()` 没有 socket，会拒绝。因此 demo server 必须走 **Hono `app.fetch(req, env)`**，
把 `env` 显式设为 `{ incoming: { socket: { remoteAddress: "127.0.0.1" } } }`——这与
“server 只绑定 127.0.0.1”的事实一致，不构成越权。

## 3. 设计

### 3.1 共享装配微调（additive）

- [`apps/api/src/acceptance-app.ts`](../../../apps/api/src/acceptance-app.ts)
  - `buildHonoApp(wiring)` 返回值增加 `fetch: (req: Request, env?: unknown) => Promise<Response>`，
    内部调用 `app.fetch(req, env)`。`request` 保持不变。
- [`tests/acceptance/harness.ts`](../../../tests/acceptance/harness.ts)
  - `AcceptanceApp` 增加只读 `fetch` 字段，透传 `server.fetch`。
  - 现有调用方（acceptance 测试、`scripts/demo.ts`）零改动。

### 3.2 新增 `scripts/demo-server.ts`

- 运行方式：`pnpm demo:web`（内部 `tsx scripts/demo-server.ts`）。
- 监听：`127.0.0.1:${BUTLER_V5_DEMO_PORT ?? 4520}`；仅 `node:http`，不引入新运行时依赖。
- 状态：`app: AcceptanceApp`、`conversationId?: string`、串行队列（chat/reset/approve/deny
  依次执行，避免 reset 与在途请求交错）。
- 输入限制：JSON body ≤ 16 KiB；`content` 为字符串且 1–2000 字符；超限返回 400。
- 路由：

| 方法 | 路径 | 行为 |
|------|------|------|
| GET | `/` | 返回自包含 HTML 控制台（内联 CSS/JS，无外链） |
| GET | `/health` | `{ ok: true, app: "butler-demo" }` |
| POST | `/demo/api/chat` | `{ content }` → 代理 `/v1/wechat/inbound`，返回 `{ reply, finalDecision, toolCalls, pending }` |
| GET | `/demo/api/approvals` | 代理 `/v1/owner/approvals` |
| POST | `/demo/api/approvals/:stepId/approve` | 代理 owner approve |
| POST | `/demo/api/approvals/:stepId/deny` | 代理 owner deny |
| POST | `/demo/api/reset` | 关闭旧 app → `makeAcceptanceApp()` 重建 → 重新写入 fixtures；`conversationId` 清空 |

- fixtures（确定性）：

```ts
plan: [
  text("你好，我是 Butler v5 demo。当前使用脚本化 LLM，不会调用真实模型。"),
  toolCall("write_file", { path: "demo-note.txt", content: "hello from demo console" }, "tc-demo-write"),
  text("已经处理完毕（demo 第三轮）。"),
]
exec: [text("✅ 已写入 demo-note.txt。"), text("demo exec 循环。")]
intake: [text("chat")]
```

- 安全边界：只绑 loopback；不转发 `x-forwarded-for` / `x-real-ip`；不读取或注入真实
  API key；`write_file` 落在 harness 的临时工作区；`app.close()` 在 SIGINT/SIGTERM 时执行。

### 3.3 控制台页面

单文件内联 HTML，含：

- 标题与状态条（服务地址、当前 `conversationId` / “新会话”）
- 消息区（用户/管家气泡，`data-testid="transcript"`）
- 输入框 + 发送按钮（Enter 发送，空内容禁用）
- 审批区：`GET /demo/api/approvals` 渲染每条待审批（capability/question），
  含「批准」「拒绝」按钮，`data-testid="approval-item"`
- 「重置会话」按钮
- 所有服务端文本用 `textContent` 注入，避免 XSS；请求失败在状态条显示中文错误

### 3.4 Playwright E2E

- 依赖：根 `devDependencies` 增加 `@playwright/test`（锁到当前可用版本 1.65.1）；
  CI 执行 `pnpm exec playwright install --with-deps chromium`。
- 新增 [`playwright.config.ts`](../../../../playwright.config.ts)：
  - `testDir: "tests/e2e-demo"`，`workers: 1`，`fullyParallel: false`
  - `use.baseURL = process.env.DEMO_BASE_URL ?? "http://127.0.0.1:4520"`
  - `webServer`: `pnpm demo:web`，`url: /health`，`timeout: 180_000`，
    `reuseExistingServer: !process.env.CI`
  - 失败时保留 trace / 截图
- 新增 `tests/e2e-demo/console.spec.ts`（用例见 §4）。
- vitest 只收集 `*.test.ts`，`tests/e2e-demo/*.spec.ts` 不会被 vitest 重复执行（已核实
  [`vitest.config.ts`](../../../vitest.config.ts)）。ESLint 若对 Playwright 导入报错，
  在用例文件顶部按现有风格处理，不放宽全局规则。

### 3.5 scripts / CI

`package.json` 新增：

```json
"demo:web": "tsx scripts/demo-server.ts",
"test:e2e:demo": "playwright test"
```

`.github/workflows/ci.yml` 新增独立 job `demo-e2e`（`needs` 不阻塞主 gate）：

1. checkout / setup-node 22 / pnpm 9.15.0 / 缓存 / `pnpm install --frozen-lockfile`
2. `pnpm exec playwright install --with-deps chromium`
3. `pnpm test:e2e:demo`
4. 失败时上传 `playwright-report/` 与 `test-results/`

### 3.6 文档

- 新增 `docs/deployment/DEMO.md`：启动方式、页面能力、安全边界、E2E 命令
- `README.md`：文档导航增加 demo 控制台入口
- `docs/TESTS.md`：新增 Playwright E2E 层说明，更新头部日期
- `docs/PROGRESS.md`：记录本次交付
- `docs/ROADMAP.md` §4：把 demo 交付项标记完成
- `docs/ENV.md`：新增 `BUTLER_V5_DEMO_PORT`（默认 `4520`，仅 demo server 读取）
- `docs/plans/README.md`：索引本 spec

## 4. E2E 用例（验收标准）

| # | 步骤 | 断言 |
|---|------|------|
| 1 | 打开 `/` | 标题可见；输入框可交互 |
| 2 | 发送“你好” | transcript 出现用户气泡 + 管家气泡，管家文本含“脚本化” |
| 3 | 发送“帮我写个文件” | 出现 `approval-item`，含 `write_file`；状态显示待审批数 1 |
| 4 | 点「批准」 | `approval-item` 消失；transcript 出现审批结果；无错误状态 |
| 5 | 点「重置会话」 | transcript 清空；待审批为 0 |
| 6 | 重置后连发两轮，点「拒绝」 | `approval-item` 消失；transcript 显示已拒绝/未执行 |

稳定性措施：Playwright 断言使用 `expect(...).toBeVisible({ timeout: 30_000 })`；
首次回合等待时间放宽到 60 s（PGlite 初始化）。

## 5. 验证清单

- `pnpm typecheck`
- `pnpm lint`
- `pnpm format:check`（先 `pnpm format`）
- `pnpm test`（全量 vitest，预期 2,423+ 通过）
- `pnpm test:e2e:demo`（新增 1 个 spec，6 条断言组）
- 手动：`pnpm demo:web` 后 `curl -s http://127.0.0.1:4520/health`

## 6. 风险与回退

| 风险 | 处理 |
|------|------|
| Playwright 版本与已缓存 chromium 不匹配 | `pnpm exec playwright install chromium` |
| PGlite 冷启动导致超时 | webServer 180 s、首回合断言 60 s |
| `app.fetch` env 注入被 Hono 版本忽略 | 若 owner 路由返回 401，改为在 demo server 内直接调用 `approveWaitingStep` / `denyWaitingStep`（回退方案） |
| CI 时长增加 | 独立 job，不影响主 gate 的时间上限 |
