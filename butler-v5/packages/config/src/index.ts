// config/index.ts
// 单 Schema 配置 — @effect/schema 定义 + 环境变量加载

import { Schema } from "@effect/schema"
import { Effect, Layer } from "effect"
import { Config } from "@butler/ports"

// ─── Schema 定义 ────────────────────────────────────────
export const ConfigSchema = Schema.Struct({
  loop: Schema.Struct({
    maxIterations: Schema.Number.pipe(Schema.int(), Schema.positive()),
    timeoutMs: Schema.Number.pipe(Schema.int(), Schema.positive()),
  }),
  guards: Schema.Struct({
    ownerOfflineThresholdMs: Schema.Number.pipe(Schema.int(), Schema.positive()),
    chaosEnabled: Schema.Boolean,
  }),
  llm: Schema.Struct({
    primary: Schema.String,
    fallback: Schema.String,
  }),
  db: Schema.Struct({
    url: Schema.String,
    maxConnections: Schema.Number.pipe(Schema.int(), Schema.positive()),
  }),
  wechat: Schema.Struct({
    token: Schema.String,
    appId: Schema.String,
    appSecret: Schema.String,
  }),
})

export type AppConfig = Schema.Schema.Type<typeof ConfigSchema>

// ─── 默认配置 ───────────────────────────────────────────
export const defaultConfig: AppConfig = {
  loop: {
    maxIterations: 50,
    timeoutMs: 600_000,
  },
  guards: {
    ownerOfflineThresholdMs: 300_000,
    chaosEnabled: false,
  },
  llm: {
    primary: "anthropic",
    fallback: "openai",
  },
  db: {
    url: "postgres://butler:butler_dev@localhost:5432/butler_v5",
    maxConnections: 10,
  },
  wechat: {
    token: "butler-dev-token",
    appId: "",
    appSecret: "",
  },
}

// ─── Config Layer（从环境变量加载，回退默认值） ──────────
export const ConfigLive = Layer.effect(
  Config,
  Effect.sync(() => {
    const env =
      (globalThis as unknown as { process?: { env?: Record<string, string | undefined> } }).process
        ?.env ?? {}
    return Config.of({
      loop: {
        maxIterations: env.LOOP_MAX_ITERATIONS
          ? parseInt(env.LOOP_MAX_ITERATIONS, 10)
          : defaultConfig.loop.maxIterations,
        timeoutMs: env.LOOP_TIMEOUT_MS
          ? parseInt(env.LOOP_TIMEOUT_MS, 10)
          : defaultConfig.loop.timeoutMs,
      },
      guards: {
        ownerOfflineThresholdMs: env.GUARDS_OWNER_OFFLINE_THRESHOLD_MS
          ? parseInt(env.GUARDS_OWNER_OFFLINE_THRESHOLD_MS, 10)
          : defaultConfig.guards.ownerOfflineThresholdMs,
        chaosEnabled: env.GUARDS_CHAOS_ENABLED === "true",
      },
      llm: {
        primary: env.LLM_PRIMARY ?? defaultConfig.llm.primary,
        fallback: env.LLM_FALLBACK ?? defaultConfig.llm.fallback,
      },
      db: {
        url: env.DATABASE_URL ?? defaultConfig.db.url,
        maxConnections: env.DB_MAX_CONNECTIONS
          ? parseInt(env.DB_MAX_CONNECTIONS, 10)
          : defaultConfig.db.maxConnections,
      },
      wechat: {
        token: env.WECHAT_TOKEN ?? defaultConfig.wechat.token,
        appId: env.WECHAT_APP_ID ?? defaultConfig.wechat.appId,
        appSecret: env.WECHAT_APP_SECRET ?? defaultConfig.wechat.appSecret,
      },
    })
  }),
)

// ─── 测试用 Layer（可覆盖默认值） ────────────────────────
export const makeTestConfig = (overrides: Partial<AppConfig> = {}) =>
  Layer.succeed(Config, Config.of({ ...defaultConfig, ...overrides }))
