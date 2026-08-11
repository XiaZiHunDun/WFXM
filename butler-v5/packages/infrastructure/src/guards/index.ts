// infrastructure/guards/guard-service-live.ts
// GuardServiceLive — 单 Layer 实现 10 条 GUARD（Phase 2–3）
// Phase 2: G-1/G-3 完整实现 + G-2/G-4/G-5/G-6/G-7/G-8 真实实现

import { Effect, Layer, Duration } from "effect"
import { GuardService } from "@butler/ports"
import type { IntentReceipt, LoopError, LoadBearingMark } from "@butler/domain"
import {
  verifyChain as pureVerifyChain,
  pickVerificationLevel,
  pickHealLayer,
} from "@butler/domain"

// ─── 内存存储 ───────────────────────────────────────────
const receiptStore = new Map<string, IntentReceipt>()
let ownerLastSeen = Date.now()

// [G-2] 承重代码标记存储
const lbMarksStore = new Map<string, LoadBearingMark>()

// [G-9] 反模式归档存储
const antiPatternArchive = new Map<
  string,
  { pattern: string; evidence: unknown; timestamp: number }
>()

// [G-10] 混沌演练调度存储
const chaosSchedules: { scenario: string; cron: string; lastRun: number }[] = []

// [G-4] 签名密钥（Phase 2: 简单 key，Phase 3: RSA/Ed25519）
const SIGNING_KEY = "butler-v5-dev-key"

// ─── 辅助函数 ───────────────────────────────────────────
function simpleHmacSign(payload: string, key: string): string {
  // Phase 2: 简单 HMAC 模拟（Phase 3 换 crypto.subtle）
  let hash = 0
  for (let i = 0; i < payload.length; i++) {
    const char = payload.charCodeAt(i)
    hash = (hash << 5) - hash + char + key.charCodeAt(i % key.length)
    hash |= 0
  }
  return `hmac-${Math.abs(hash).toString(16)}`
}

function simpleHmacVerify(payload: string, sig: string, key: string): boolean {
  return simpleHmacSign(payload, key) === sig
}

// ─── GuardServiceLive ───────────────────────────────────
export const GuardServiceLive = Layer.effect(
  GuardService,
  Effect.sync(() => {
    return GuardService.of({
      // [G-1] 签发 IntentReceipt
      issueReceipt: (input) =>
        Effect.sync(() => {
          const receipt: IntentReceipt = {
            id: crypto.randomUUID(),
            intent: input.intent,
            evidenceFiles: input.evidenceFiles,
            locDelta: input.locDelta,
            chainCompleteness: 1,
            guardFindings: [],
            authorAgent: input.authorAgent,
            createdAt: Date.now(),
          }
          receiptStore.set(receipt.id, receipt)
          return receipt
        }),

      // [G-2] 承重代码检查
      checkLoadBearing: (path, op) =>
        Effect.sync(() => {
          const mark = lbMarksStore.get(path)
          if (mark && mark.ownerApproved) {
            return {
              allowed: false,
              reason: `承重代码 "${path}" 被标记为 "${mark.reason}"，${op === "delete" ? "删除" : "写入"} 需 Owner 签名`,
            }
          }
          return { allowed: true }
        }),

      // [G-3] Owner 离线策略
      checkOwnerOnline: (action) =>
        Effect.sync(() => {
          const offlineMs = Date.now() - ownerLastSeen
          const threshold = 300_000 // 5 分钟
          if (offlineMs > threshold) {
            if (action.category === "read") {
              return { decision: "allow" as const, reason: "read-only action allowed" }
            }
            if (action.category === "write" || action.category === "execute") {
              return { decision: "deny" as const, reason: "Owner offline, write/execute blocked" }
            }
            return { decision: "queue" as const, reason: "Owner offline, action queued" }
          }
          return { decision: "allow" as const, reason: "Owner online" }
        }),

      // [G-4] HUMAN 签名验证
      verifyHumanSig: (sig, payload) =>
        Effect.sync(() => {
          const payloadStr = typeof payload === "string" ? payload : JSON.stringify(payload)
          return simpleHmacVerify(payloadStr, sig, SIGNING_KEY)
        }),

      // [G-5] 多文件链路校验
      verifyChain: (spec, files) => Effect.sync(() => pureVerifyChain(spec, files)),

      // [G-6] 验证级别选择
      pickVerification: (delta, isGen) => Effect.sync(() => pickVerificationLevel(delta, isGen)),

      // [G-7] 角色分离
      checkRoleSeparation: (author, reviewer) =>
        Effect.sync(() => {
          if (author === reviewer) {
            return { ok: false, reason: `Author "${author}" cannot review own work` }
          }
          return { ok: true }
        }),

      // [G-8] 3 层自愈：Retry → Fallback → OwnerNotify
      heal: <A, E>(
        effect: Effect.Effect<A, E>,
        options?: { readonly maxRetry?: number; readonly fallback?: () => Effect.Effect<A, E> },
      ) =>
        Effect.gen(function* (_) {
          const maxRetry = options?.maxRetry ?? 3
          let retryCount = 0

          while (retryCount < maxRetry) {
            const result = yield* _(Effect.either(effect))
            if (result._tag === "Right") return result.right

            const error = result.left as LoopError
            const layer = pickHealLayer(error as LoopError, retryCount)

            if (layer === "retry") {
              retryCount++
              yield* _(Effect.sleep(Duration.millis(100 * Math.pow(2, retryCount))))
              continue
            }

            if (layer === "fallback" && options?.fallback) {
              return yield* _(options.fallback())
            }

            // owner-notify: 直接抛出错误
            return yield* _(Effect.fail(error))
          }

          // 超过最大重试次数
          if (options?.fallback) {
            return yield* _(options.fallback())
          }
          return yield* _(
            Effect.fail({
              _tag: "GuardRejected",
              reason: { _tag: "HealFailed", layer: "owner-notify" },
            } as unknown as E),
          )
        }),

      // [G-9] 反模式归档（Owner 手动触发）
      archiveAntiPattern: (pattern, evidence) =>
        Effect.sync(() => {
          const archiveDir = ".butler/anti-patterns/"
          const timestamp = Date.now()
          const filename = `${archiveDir}${pattern}-${timestamp}.json`
          // Phase 3: 内存存储（Phase 4: 写文件）
          antiPatternArchive.set(pattern, { pattern, evidence, timestamp })
          Effect.logInfo(`[G-9] Anti-pattern archived: ${filename}`)
        }),

      // [G-10] 混沌演练调度（每月 1 次，默认关闭）
      scheduleChaos: (scenario, cron) =>
        Effect.sync(() => {
          chaosSchedules.push({ scenario, cron, lastRun: 0 })
          Effect.logInfo(`[G-10] Chaos scheduled: ${scenario} (${cron})`)
        }),

      // 契约加载：只加载 AGENTS.md + .cursorrules（不含 .blackboard/README.md）
      loadContract: () =>
        Effect.sync(() => {
          // Phase 3: 加载内置契约规则（Phase 4: 从文件系统加载 AGENTS.md + .cursorrules）
          return {
            loadedFiles: ["AGENTS.md", ".cursorrules"],
            rules: [
              { pattern: "import \\*", severity: "BLOCK" as const, source: ".cursorrules" },
              { pattern: "delete __all__", severity: "WARN" as const, source: ".cursorrules" },
              { pattern: "CONSOLE_LOG", severity: "WARN" as const, source: "AGENTS.md" },
            ],
            loadedAt: Date.now(),
          }
        }),
    })
  }),
)

// ─── 测试辅助 ───────────────────────────────────────────
export function simOwnerOffline() {
  ownerLastSeen = 0
}

export function simOwnerOnline() {
  ownerLastSeen = Date.now()
}

// [G-2] 测试辅助：注册承重代码标记
export function registerLoadBearingMark(mark: LoadBearingMark) {
  lbMarksStore.set(mark.path, mark)
}

export function clearLoadBearingMarks() {
  lbMarksStore.clear()
}

// [G-4] 测试辅助：签名
export function signPayload(payload: unknown): string {
  const payloadStr = typeof payload === "string" ? payload : JSON.stringify(payload)
  return simpleHmacSign(payloadStr, SIGNING_KEY)
}
