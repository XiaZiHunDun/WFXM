/**
 * Local tracing — DESIGN §12.
 * Default: structured local events. OTEL exporter is optional, not a runtime dep.
 */

export type TraceKind = "run" | "step" | "capability" | "policy" | "grant" | "approval"

/**
 * D23: provider-agnostic token usage surfaced by `LLMAdapter.complete`.
 * Mirrors `packages/adapters/src/llm-provider.ts:LLMUsage` so trace
 * events can carry the same shape across the boundary without an
 * adapter import (the domain layer stays free of adapter imports).
 */
export interface TraceTokenUsage {
  readonly inputTokens: number
  readonly outputTokens: number
  readonly totalTokens: number
}

export interface TraceEvent {
  readonly id: string
  readonly kind: TraceKind
  readonly name: string
  readonly status: "ok" | "error" | "waiting"
  /**
   * Phase 5 P0: inbound turn id threaded from intake through Run / LLM /
   * subagent / approval so owner reports can be correlated with traces.
   */
  readonly turnId: string | null
  readonly conversationId: string | null
  readonly runId: string | null
  readonly stepId: string | null
  readonly parentRunId: string | null
  readonly subject: string | null
  readonly triggerSource: string | null
  readonly capability: string | null
  readonly policyDecision: string | null
  readonly grantId: string | null
  readonly waitingStepId: string | null
  readonly durationMs: number | null
  /**
   * D23: LLM token usage (input / output / total). First-class so §14
   * `token` field is captured by `TraceEvent` rather than smuggled
   * through `detail`. `null` when no LLM call was made or when the
   * adapter did not surface usage (legacy fixtures).
   */
  readonly token: TraceTokenUsage | null
  /**
   * D23: USD cost of the LLM call. Reserved for a future pricing-env-
   * var batch (`BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK` etc.); stays
   * `null` until that lands. Declared first-class so §14 `cost` is
   * covered by the trace shape from the start.
   */
  readonly costUsd: number | null
  readonly detail: Readonly<Record<string, unknown>>
  readonly createdAt: number
}

/**
 * Phase 6: a "failed run" appears in two shapes in the wild.
 *   - legacy step event: `kind="step", name="run_failed"`
 *   - current emitters (run-engine / butler loop): `kind="run"`,
 *     `name="failure" | "finish"`, `status="error"`
 * Counting only the legacy shape silently reports zero failures, which is
 * exactly what the weekly digest used to do. Both readers (`/周报`,
 * `/v1/owner/usage`) must use this predicate.
 */
export function isFailedRunTrace(event: Pick<TraceEvent, "kind" | "name" | "status">): boolean {
  if (event.kind === "step" && event.name === "run_failed") return true
  if (event.kind === "run" && (event.name === "failure" || event.name === "finish")) {
    return event.status === "error"
  }
  return false
}

export interface CreateTraceEventInput {
  readonly kind: TraceKind
  readonly name: string
  readonly status?: TraceEvent["status"]
  readonly turnId?: string | null
  readonly conversationId?: string | null
  readonly runId?: string | null
  readonly stepId?: string | null
  readonly parentRunId?: string | null
  readonly subject?: string | null
  readonly triggerSource?: string | null
  readonly capability?: string | null
  readonly policyDecision?: string | null
  readonly grantId?: string | null
  readonly waitingStepId?: string | null
  readonly durationMs?: number | null
  readonly token?: TraceTokenUsage | null
  readonly costUsd?: number | null
  readonly detail?: Readonly<Record<string, unknown>>
  readonly nowMs?: number
  readonly id?: string
}

export type TraceExporterKind = "off" | "stdout"

export interface TraceConfig {
  /** When false, recordTrace is a no-op. */
  readonly enabled: boolean
  readonly redact: boolean
  readonly maxEvents: number
  readonly exporter: TraceExporterKind
}

const SECRET_PATTERNS: readonly RegExp[] = [
  /\b(sk-[a-zA-Z0-9_-]{8,})\b/g,
  /\b(ghp_[a-zA-Z0-9]{20,})\b/g,
  /\b(AKIA[0-9A-Z]{16})\b/g,
  /\b(eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)\b/g,
  /\b(Bearer\s+)[A-Za-z0-9._\-+=/]+/gi,
  /\b(api[_-]?key|token|password|secret)\s*[:=]\s*["']?[^\s"',}]+/gi,
]

export function redactTraceText(text: string): string {
  let out = text
  for (const pattern of SECRET_PATTERNS) {
    out = out.replace(pattern, (match, g1?: string) => {
      if (typeof g1 === "string" && match.toLowerCase().startsWith("bearer")) {
        return `${g1}***`
      }
      if (typeof g1 === "string" && /api|token|password|secret/i.test(g1)) {
        return `${g1}=***`
      }
      return "***"
    })
  }
  return out
}

/**
 * 深度上限 8：RAG 证据是 detail.meta.retrieval.hits[].{text,title,...}
 * 五层嵌套，旧的 4 层上限会把每个 hit 的字段值都替换成 "[truncated]"，
 * 导致 audit / trace 里没有可用的检索上下文。仍保留上限防止无限递归。
 */
export function redactTraceValue(value: unknown, depth = 0): unknown {
  if (depth > 8) return "[truncated]"
  if (typeof value === "string") return redactTraceText(value)
  if (Array.isArray(value)) return value.slice(0, 20).map((v) => redactTraceValue(v, depth + 1))
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>).slice(0, 40)) {
      if (/token|password|secret|authorization|apiKey|api_key/i.test(k)) {
        out[k] = "***"
      } else {
        out[k] = redactTraceValue(v, depth + 1)
      }
    }
    return out
  }
  return value
}

export function createTraceEvent(input: CreateTraceEventInput): TraceEvent {
  return {
    id: input.id ?? crypto.randomUUID(),
    kind: input.kind,
    name: input.name,
    status: input.status ?? "ok",
    turnId: input.turnId ?? null,
    conversationId: input.conversationId ?? null,
    runId: input.runId ?? null,
    stepId: input.stepId ?? null,
    parentRunId: input.parentRunId ?? null,
    subject: input.subject ?? null,
    triggerSource: input.triggerSource ?? null,
    capability: input.capability ?? null,
    policyDecision: input.policyDecision ?? null,
    grantId: input.grantId ?? null,
    waitingStepId: input.waitingStepId ?? null,
    durationMs: input.durationMs ?? null,
    token: input.token ?? null,
    costUsd: input.costUsd ?? null,
    detail: (input.detail ?? {}) as Readonly<Record<string, unknown>>,
    createdAt: input.nowMs ?? Date.now(),
  }
}

export function applyTraceRedaction(event: TraceEvent): TraceEvent {
  return {
    ...event,
    detail: redactTraceValue(event.detail) as Readonly<Record<string, unknown>>,
    name: redactTraceText(event.name),
    subject: event.subject ? redactTraceText(event.subject) : null,
    capability: event.capability ? redactTraceText(event.capability) : null,
  }
}

function envTruthy(raw: string | undefined, defaultWhenUnset: boolean): boolean {
  if (raw === undefined || raw.trim() === "") return defaultWhenUnset
  const text = raw.trim().toLowerCase()
  if (text === "0" || text === "false" || text === "no" || text === "off") return false
  if (text === "1" || text === "true" || text === "yes" || text === "on") return true
  return defaultWhenUnset
}

export function parseTraceConfig(
  env: Readonly<Record<string, string | undefined>> = {},
): TraceConfig {
  const enabled = envTruthy(env["BUTLER_V5_TRACE"], true)
  const redact = envTruthy(env["BUTLER_V5_TRACE_REDACT"], true)
  const maxRaw = Number(env["BUTLER_V5_TRACE_MAX_EVENTS"] ?? 500)
  const maxEvents = Number.isFinite(maxRaw) && maxRaw > 0 ? Math.floor(maxRaw) : 500
  const exporterRaw = (env["BUTLER_V5_OTEL_EXPORTER"] ?? "off").trim().toLowerCase()
  const exporter: TraceExporterKind = exporterRaw === "stdout" ? "stdout" : "off"
  return { enabled, redact, maxEvents, exporter }
}

export interface TraceRetentionConfig {
  /** Delete trace rows older than this many days. */
  readonly retentionDays: number
  /** Hard cap on persisted trace rows; oldest rows are evicted first. */
  readonly maxRows: number
}

/** Parse retention policy from env (defaults: 30 days / 200k rows). */
export function parseTraceRetention(
  env: Readonly<Record<string, string | undefined>> = {},
): TraceRetentionConfig {
  const daysRaw = Number(env["BUTLER_V5_TRACE_RETENTION_DAYS"] ?? 30)
  const retentionDays = Number.isFinite(daysRaw) && daysRaw > 0 ? Math.floor(daysRaw) : 30
  const rowsRaw = Number(env["BUTLER_V5_TRACE_MAX_ROWS"] ?? 200000)
  const maxRows = Number.isFinite(rowsRaw) && rowsRaw > 0 ? Math.floor(rowsRaw) : 200000
  return { retentionDays, maxRows }
}

/** Minimal OTLP-ish JSON line for stdout exporter (not a full SDK). */
export function formatOtelStdoutLine(event: TraceEvent): string {
  return JSON.stringify({
    resourceSpans: [
      {
        scopeSpans: [
          {
            spans: [
              {
                traceId: (event.runId ?? event.id).replace(/-/g, "").padEnd(32, "0").slice(0, 32),
                spanId: event.id.replace(/-/g, "").slice(0, 16),
                name: `${event.kind}:${event.name}`,
                kind: 1,
                startTimeUnixNano: String(event.createdAt * 1_000_000),
                endTimeUnixNano: String((event.createdAt + (event.durationMs ?? 0)) * 1_000_000),
                attributes: [
                  { key: "butler.kind", value: { stringValue: event.kind } },
                  { key: "butler.status", value: { stringValue: event.status } },
                  ...(event.turnId
                    ? [{ key: "butler.turnId", value: { stringValue: event.turnId } }]
                    : []),
                  ...(event.conversationId
                    ? [
                        {
                          key: "butler.conversationId",
                          value: { stringValue: event.conversationId },
                        },
                      ]
                    : []),
                  ...(event.runId
                    ? [{ key: "butler.runId", value: { stringValue: event.runId } }]
                    : []),
                  ...(event.capability
                    ? [
                        {
                          key: "butler.capability",
                          value: { stringValue: event.capability },
                        },
                      ]
                    : []),
                  ...(event.policyDecision
                    ? [
                        {
                          key: "butler.policyDecision",
                          value: { stringValue: event.policyDecision },
                        },
                      ]
                    : []),
                  ...(event.token
                    ? [
                        {
                          key: "butler.token.inputTokens",
                          value: { intValue: String(event.token.inputTokens) },
                        },
                        {
                          key: "butler.token.outputTokens",
                          value: { intValue: String(event.token.outputTokens) },
                        },
                        {
                          key: "butler.token.totalTokens",
                          value: { intValue: String(event.token.totalTokens) },
                        },
                      ]
                    : []),
                  ...(event.costUsd !== null
                    ? [
                        {
                          key: "butler.costUsd",
                          value: { doubleValue: event.costUsd },
                        },
                      ]
                    : []),
                ],
                status: {
                  code: event.status === "error" ? 2 : event.status === "waiting" ? 0 : 1,
                },
              },
            ],
          },
        ],
      },
    ],
  })
}

export function filterTraceEvents(
  events: readonly TraceEvent[],
  filter: {
    readonly runId?: string
    readonly conversationId?: string
    readonly turnId?: string
    readonly kind?: TraceKind
    readonly limit?: number
  },
): readonly TraceEvent[] {
  const limit = filter.limit ?? 100
  if (limit <= 0) return []
  return events
    .filter((e) => (filter.runId ? e.runId === filter.runId : true))
    .filter((e) => (filter.conversationId ? e.conversationId === filter.conversationId : true))
    .filter((e) => (filter.turnId ? e.turnId === filter.turnId : true))
    .filter((e) => (filter.kind ? e.kind === filter.kind : true))
    .slice(-limit)
}
