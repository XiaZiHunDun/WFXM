import { describe, it, expect } from "vitest"
import { Effect, Stream } from "effect"
import { MockWeChatLive } from "./index.js"
import { WeChatGateway } from "@butler/ports"

describe("infrastructure/wechat", () => {
  it("send logs message", async () => {
    const program = Effect.gen(function* () {
      const wechat = yield* WeChatGateway
      yield* wechat.send("wx-owner", "Hello from Butler")
      return true
    })

    const result = await Effect.runPromise(Effect.provide(program, MockWeChatLive))
    expect(result).toBe(true)
  })

  it("receive returns empty stream", async () => {
    const program = Effect.gen(function* () {
      const wechat = yield* WeChatGateway
      const messages = yield* wechat.receive().pipe(Stream.runCollect)
      return Array.from(messages)
    })

    const result = await Effect.runPromise(Effect.provide(program, MockWeChatLive))
    expect(result).toEqual([])
  })

  it("verifySignature returns true in mock", async () => {
    const program = Effect.gen(function* () {
      const wechat = yield* WeChatGateway
      return yield* wechat.verifySignature("sig", "123", "abc")
    })

    const result = await Effect.runPromise(Effect.provide(program, MockWeChatLive))
    expect(result).toBe(true)
  })
})
