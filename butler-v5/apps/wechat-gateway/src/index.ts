// @butler/wechat-gateway — leftover Phase 3 stub.
// Native iLink long-poll lives in @butler/api (`ilink-poller.ts`) and
// starts from `butler start` when BUTLER_V5_ILINK_ENABLED=1.

import { Effect } from "effect"
import { WeChatGatewayLive } from "@butler/infrastructure"

const main = Effect.gen(function* () {
  yield* Effect.logInfo("[WeChat Gateway] Starting...")
  yield* Effect.logInfo(
    "[WeChat Gateway] Stub process — enable BUTLER_V5_ILINK_ENABLED=1 on butler start instead",
  )
  yield* Effect.never
})

// 启动
Effect.runPromise(Effect.provide(main, WeChatGatewayLive)).catch(() => {
  // eslint-disable-next-line no-console
  console.error("[WeChat Gateway] Fatal error")
  const proc = (globalThis as { process?: { exit: (code: number) => void } }).process
  if (proc) proc.exit(1)
})
