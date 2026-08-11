// @butler/wechat-gateway — 微信入站 + 出站网关
// Phase 3 实现

import { Effect } from "effect"
import { WeChatGatewayLive } from "@butler/infrastructure"

// ─── 微信网关启动入口 ───────────────────────────────────
const main = Effect.gen(function* () {
  yield* Effect.logInfo("[WeChat Gateway] Starting...")

  // Phase 3: 启动 WeChatGateway（Phase 4: 接入真实微信回调）
  yield* Effect.logInfo("[WeChat Gateway] Ready (stub mode)")
  yield* Effect.never
})

// 启动
Effect.runPromise(Effect.provide(main, WeChatGatewayLive)).catch(() => {
  // eslint-disable-next-line no-console
  console.error("[WeChat Gateway] Fatal error")
  const proc = (globalThis as { process?: { exit: (code: number) => void } }).process
  if (proc) proc.exit(1)
})
