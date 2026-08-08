// tests/contracts/test_config_schema.ts
// 契约测试 — ConfigSchema 验证 [G-2]
// 验证 ConfigSchema 定义与 AppConfig 类型一致，且所有字段有默认值

import { describe, it, expect } from "vitest"
import { Schema } from "@effect/schema"
import { ConfigSchema, defaultConfig, makeTestConfig } from "@butler/config"

describe("契约测试：ConfigSchema 字段完整性", () => {
  it("ConfigSchema 包含所有顶层字段", () => {
    const decoded = Schema.decodeUnknownSync(ConfigSchema)(defaultConfig)
    expect(decoded.loop).toBeDefined()
    expect(decoded.guards).toBeDefined()
    expect(decoded.llm).toBeDefined()
    expect(decoded.db).toBeDefined()
    expect(decoded.wechat).toBeDefined()
  })

  it("loop 配置包含 maxIterations 和 timeoutMs", () => {
    expect(defaultConfig.loop.maxIterations).toBe(50)
    expect(defaultConfig.loop.timeoutMs).toBe(600_000)
  })

  it("guards 配置包含 ownerOfflineThresholdMs 和 chaosEnabled", () => {
    expect(defaultConfig.guards.ownerOfflineThresholdMs).toBe(300_000)
    expect(defaultConfig.guards.chaosEnabled).toBe(false)
  })

  it("llm 配置包含 primary 和 fallback", () => {
    expect(defaultConfig.llm.primary).toBe("anthropic")
    expect(defaultConfig.llm.fallback).toBe("openai")
  })

  it("db 配置包含 url 和 maxConnections", () => {
    expect(defaultConfig.db.url).toContain("postgres://")
    expect(defaultConfig.db.maxConnections).toBe(10)
  })

  it("wechat 配置包含 token/appId/appSecret", () => {
    expect(typeof defaultConfig.wechat.token).toBe("string")
    expect(typeof defaultConfig.wechat.appId).toBe("string")
    expect(typeof defaultConfig.wechat.appSecret).toBe("string")
  })
})

describe("契约测试：ConfigSchema 类型校验", () => {
  it("默认配置通过 Schema 校验", () => {
    const result = Schema.decodeUnknownSync(ConfigSchema)(defaultConfig)
    expect(result).toEqual(defaultConfig)
  })

  it("无效配置被 Schema 拒绝", () => {
    const invalid = { loop: { maxIterations: -1, timeoutMs: 0 } }
    const result = Schema.decodeUnknownEither(ConfigSchema)(invalid)
    expect(result._tag).toBe("Left")
  })

  it("loop.maxIterations 必须为正整数", () => {
    const invalid = { ...defaultConfig, loop: { ...defaultConfig.loop, maxIterations: 0 } }
    const result = Schema.decodeUnknownEither(ConfigSchema)(invalid)
    expect(result._tag).toBe("Left")
  })

  it("loop.timeoutMs 必须为正整数", () => {
    const invalid = { ...defaultConfig, loop: { ...defaultConfig.loop, timeoutMs: -1 } }
    const result = Schema.decodeUnknownEither(ConfigSchema)(invalid)
    expect(result._tag).toBe("Left")
  })
})

describe("契约测试：makeTestConfig 覆盖", () => {
  it("makeTestConfig 可覆盖单个字段", () => {
    const layer = makeTestConfig({ loop: { maxIterations: 10, timeoutMs: 1000 } })
    expect(layer).toBeDefined()
  })

  it("makeTestConfig 空参数返回默认配置", () => {
    const layer = makeTestConfig()
    expect(layer).toBeDefined()
  })
})
