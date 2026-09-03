/**
 * 测试支撑：从注入的 Wiring 构建一个挂载生产入站路由的全新 Hono app。
 *
 * 仅供 tests/acceptance 使用 —— 之所以放在 apps/api/src：`hono` 与
 * `createRoutes` 只在 apps/api 内部解析（hono 是 apps/api 的直接依赖，root
 * 不可见），tests/ 直接 import hono 会失败。此处只做薄封装，不接生产 wiring、
 * 不触发副作用；真实入站逻辑仍在 `createRoutes` 内未被绕过。
 */
import { Hono } from "hono"
import { createRoutes } from "./routes.js"
import type { Wiring } from "./wiring.js"

// ts-prune-ignore-next: 仅被 tests/acceptance 使用（tests 不参与 ts-prune 扫描）。
export function buildHonoApp(wiring: Wiring): {
  readonly request: (path: string, init: RequestInit) => Promise<Response>
} {
  const app = new Hono()
  createRoutes(app, wiring)
  // Hono 的 `app.request` 签名为 `Response | Promise<Response>`，统一收敛为
  // `Promise<Response>` 以匹配 tests/acceptance harness 的 typed request 接口。
  return {
    request: (path, init) => Promise.resolve(app.request(path, init)),
  }
}