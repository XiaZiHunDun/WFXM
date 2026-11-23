# 本地 Demo 控制台

> **用途**：一条命令在浏览器里体验 Butler v5 的主链路——发消息、收到回复、触发审批、
> 批准 / 拒绝、重置会话。
> **入口**：`pnpm demo:web` → <http://127.0.0.1:4520>
> **定位**：开发者 / 评估用 demo，不是生产 Web UI。

## 快速开始

```bash
cd butler-v5
pnpm demo:web
# 浏览器打开 http://127.0.0.1:4520
```

首次启动需要初始化内存 PGlite，通常几秒内就绪。`GET /health` 返回
`{"ok":true,"app":"butler-demo"}` 即表示可用。

端口可覆盖（仅监听 `127.0.0.1`）：

```bash
BUTLER_V5_DEMO_PORT=4600 pnpm demo:web
```

## 页面上能做什么

| 操作 | 说明 |
|------|------|
| 发送消息 | 等价于 `POST /v1/wechat/inbound`，回复来自脚本化 LLM |
| 查看待审批 | 右侧栏展示 `GET /v1/owner/approvals` 的待审批项（能力名 + 确认文案） |
| 批准 / 拒绝 | 走 `POST /v1/owner/approvals/:stepId/approve|deny`，刷新待审批列表 |
| 重置会话 | 关闭并重建 demo app（内存库 + fixture 计数清零），消息区清空 |

确定性剧本（fixture）：

1. 第 1 轮 → 文本回复
2. 第 2 轮 → `write_file`（命中审批策略 → 等待审批）
3. 第 3 轮 → 文本回复

在第 2 轮后点「批准」，会真实执行一次 `write_file`（写入 harness 的临时工作区）；
点「拒绝」则不会执行。

## 安全边界

- **只绑定 loopback**：`127.0.0.1`，不接受局域网 / 公网访问。
- **不接真实模型**：复用 `tests/acceptance/harness.ts` 的 fixture LLM，不需要
  `ANTHROPIC_API_KEY` / `MINIMAX_API_KEY`。
- **不碰真实工作区**：数据库为内存 PGlite；`BUTLER_V5_WORKSPACE_ROOT` 指向临时目录，
  demo 退出时清理。
- **不开启 MCP**：`BUTLER_V5_MCP_ENABLED=0`。
- 请求体上限 16 KiB，消息上限 2000 字符。

## API（demo 内部）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 控制台页面 |
| GET | `/health` | 健康检查 |
| POST | `/demo/api/chat` | `{ "content": "..." }` → `{ reply, finalDecision, toolCalls, pending }` |
| GET | `/demo/api/approvals` | 待审批列表 |
| POST | `/demo/api/approvals/:stepId/approve` | 批准 |
| POST | `/demo/api/approvals/:stepId/deny` | 拒绝 |
| POST | `/demo/api/reset` | 重建会话 |

这些路径只存在于 demo server，不在生产 API 表面内。

## E2E 与 CI

```bash
pnpm exec playwright install chromium   # 首次
pnpm test:e2e:demo
```

Playwright 配置见根目录 `playwright.config.ts`：`webServer` 自动执行 `pnpm demo:web`
并等待 `/health`；用例位于 `tests/e2e-demo/console.spec.ts`。CI 中由独立 job
`demo-e2e` 执行，失败时上传 `playwright-report/` 与 `test-results/`。

## 排障

| 现象 | 处理 |
|------|------|
| 端口被占用 | `BUTLER_V5_DEMO_PORT=<空闲端口> pnpm demo:web` |
| Playwright 报浏览器不存在 | `pnpm exec playwright install chromium` |
| 页面一直「处理中…」 | 查看终端日志；`/health` 是否 200 |
| 待审批一直不出现 | 确认已发送第 2 轮消息；fixture 按轮次回放，重置后从头开始 |
