// shared/index.ts
// 跨包通用工具 — 品牌类型、基准测试、日志工具

// ─── 品牌类型工具 ──────────────────────────────────────
export type Brand<K extends string> = { readonly __brand: K }

// ─── 基准测试工具 ──────────────────────────────────────
export function bench<T>(label: string, fn: () => T): T {
  const start = performance.now()
  const result = fn()
  const elapsed = performance.now() - start
  if (elapsed > 100) {
    // console.warn is the intended output for the bench utility
    // eslint-disable-next-line no-console
    console.warn(`[bench] ${label}: ${elapsed.toFixed(2)}ms (slow)`)
  }
  return result
}

// ─── 日志级别 ──────────────────────────────────────────
export type LogLevel = "debug" | "info" | "warn" | "error"

export function createLogger(namespace: string) {
  return {
    debug: (msg: string, ...args: unknown[]) => {
      // console.debug is the backing implementation of the debug log level
      // eslint-disable-next-line no-console
      if (isDebugEnabled()) console.debug(`[${namespace}] ${msg}`, ...args)
    },
    info: (msg: string, ...args: unknown[]) => {
      // console.info is the backing implementation of the info log level
      // eslint-disable-next-line no-console
      console.info(`[${namespace}] ${msg}`, ...args)
    },
    warn: (msg: string, ...args: unknown[]) => {
      // console.warn is the backing implementation of the warn log level
      // eslint-disable-next-line no-console
      console.warn(`[${namespace}] ${msg}`, ...args)
    },
    error: (msg: string, ...args: unknown[]) => {
      // console.error is the backing implementation of the error log level
      // eslint-disable-next-line no-console
      console.error(`[${namespace}] ${msg}`, ...args)
    },
  }
}

function isDebugEnabled(): boolean {
  const env =
    (globalThis as unknown as { process?: { env?: Record<string, string | undefined> } }).process
      ?.env ?? {}
  return env["DEBUG"] === "1" || env["BUTLER_LOG_LEVEL"] === "debug"
}

// ─── 深冻结 ────────────────────────────────────────────
export function deepFreeze<T extends Record<string, unknown>>(obj: T): Readonly<T> {
  Object.freeze(obj)
  for (const key of Object.keys(obj)) {
    const val: unknown = obj[key]
    if (val !== null && typeof val === "object" && !Object.isFrozen(val)) {
      deepFreeze(val as Record<string, unknown>)
    }
  }
  return obj
}
