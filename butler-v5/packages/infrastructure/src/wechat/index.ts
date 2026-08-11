// infrastructure/wechat — 微信 SDK 封装（消息收发 + 签名验证）
// Phase 3 实现

import { Effect, Layer, Stream } from "effect"
import { WeChatGateway } from "@butler/ports"

// ─── WeChatGatewayLive（Phase 3: 骨架，Phase 4: 接入真实微信 API） ──
export const WeChatGatewayLive = Layer.effect(
  WeChatGateway,
  Effect.sync(() => {
    return WeChatGateway.of({
      send: (to, content) => Effect.logInfo(`[WeChat] → ${to}: ${content.slice(0, 100)}`),

      receive: () => Stream.fromIterable([]),

      verifySignature: (signature, timestamp, nonce) =>
        Effect.sync(() => {
          // Phase 3: 简单验证（Phase 4: SHA1 排序比较）
          const globalProcess = (
            globalThis as { process?: { env?: Record<string, string | undefined> } }
          ).process
          const env = globalProcess?.env ?? {}
          const token = env["WECHAT_TOKEN"] ?? "butler-dev-token"
          const sorted = [token, timestamp, nonce].sort().join("")
          // 简化：直接返回 true（Phase 4 实现 SHA1）
          return sorted.length > 0 && signature.length > 0
        }),
    })
  }),
)

// ─── 测试用 Mock WeChat ─────────────────────────────────
export const MockWeChatLive = Layer.succeed(
  WeChatGateway,
  WeChatGateway.of({
    send: () => Effect.void,
    receive: () => Stream.fromIterable([]),
    verifySignature: () => Effect.succeed(true),
  }),
)
