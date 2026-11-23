import { defineConfig, devices } from "@playwright/test"

const port = Number.parseInt(process.env["BUTLER_V5_DEMO_PORT"] ?? "4520", 10) || 4520
const baseURL = process.env["DEMO_BASE_URL"] ?? `http://127.0.0.1:${port}`

/**
 * Demo 控制台 E2E — 只跑 tests/e2e-demo 下的 *.spec.ts。
 *
 * webServer 用 `pnpm demo:web` 起本地控制台（脚本化 LLM + 内存 PGlite），
 * 通过 /health 等就绪。CI 下不复用已有进程，本地开发可复用。
 */
export default defineConfig({
  testDir: "tests/e2e-demo",
  fullyParallel: false,
  workers: 1,
  forbidOnly: process.env["CI"] !== undefined,
  retries: 0,
  reporter: process.env["CI"] !== undefined ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer:
    process.env["DEMO_BASE_URL"] !== undefined
      ? undefined
      : {
          command: "pnpm demo:web",
          url: `${baseURL}/health`,
          timeout: 180_000,
          reuseExistingServer: process.env["CI"] === undefined,
          env: { BUTLER_V5_DEMO_PORT: String(port) },
        },
})
