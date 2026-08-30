// config/index.ts
// 单 Schema 配置 — @effect/schema 定义 + 环境变量加载
//
// 从 R2 Effect Tag（`Config` of `@butler/ports`，at R11.2 归档至
// `_archive/packages/ports-effect-tag-scaffold/`）改为纯函数 + `process.env`
// 直读（DESIGN §10 + R12 PRD §5 CP-2）。已无 Effect Layer 依赖。

import { Schema } from "@effect/schema"

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

// ─── Env 加载 ──────────────────────────────────────────
const parseInt10 = (v: string | undefined, fallback: number): number => {
  if (!v) return fallback
  const n = parseInt(v, 10)
  return Number.isFinite(n) ? n : fallback
}

/** 从 process.env（或传入的 env map）加载 AppConfig，应用 defaultConfig 作为兜底。 */
export function loadConfig(
  env: Readonly<Record<string, string | undefined>> = (globalThis as unknown as {
    process?: { env?: Record<string, string | undefined> }
  }).process?.env ?? {},
): AppConfig {
  const merged = env as Record<string, string | undefined>
  return {
    loop: {
      maxIterations: parseInt10(merged.LOOP_MAX_ITERATIONS, defaultConfig.loop.maxIterations),
      timeoutMs: parseInt10(merged.LOOP_TIMEOUT_MS, defaultConfig.loop.timeoutMs),
    },
    guards: {
      ownerOfflineThresholdMs: parseInt10(
        merged.GUARDS_OWNER_OFFLINE_THRESHOLD_MS,
        defaultConfig.guards.ownerOfflineThresholdMs,
      ),
      chaosEnabled: merged.GUARDS_CHAOS_ENABLED === "true",
    },
    llm: {
      primary: merged.LLM_PRIMARY ?? defaultConfig.llm.primary,
      fallback: merged.LLM_FALLBACK ?? defaultConfig.llm.fallback,
    },
    db: {
      url: merged.DATABASE_URL ?? defaultConfig.db.url,
      maxConnections: parseInt10(merged.DB_MAX_CONNECTIONS, defaultConfig.db.maxConnections),
    },
    wechat: {
      token: merged.WECHAT_TOKEN ?? defaultConfig.wechat.token,
      appId: merged.WECHAT_APP_ID ?? defaultConfig.wechat.appId,
      appSecret: merged.WECHAT_APP_SECRET ?? defaultConfig.wechat.appSecret,
    },
  }
}

/** 测试用 Config 对象（不再是 Effect Layer）。 */
export const makeTestConfig = (overrides: Partial<AppConfig> = {}): AppConfig => ({
  ...defaultConfig,
  ...overrides,
})
