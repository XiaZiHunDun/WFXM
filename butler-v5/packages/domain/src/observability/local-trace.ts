/**
 * Local tracing — DESIGN §12.
 * Default: structured local events. OTEL exporter is optional, not a runtime dep.
 */

export type TraceKind =
  | "run"
  | "step"
  | "capability"
  | "policy"
  | "grant"
  | "approval"

export interface TraceEvent {
  readonly id: string
  readonly kind: TraceKind
  readonly name: string
  readonly status: "ok" | "error" | "waiting"
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
  readonly detail: Readonly<Record<string, unknown>>
  readonly createdAt: number
}

export interface CreateTraceEventInput {
  readonly kind: TraceKind
  readonly name: string
  readonly status?: TraceEvent["status"]
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

export function redactTraceValue(value: unknown, depth = 0): unknown {
  if (depth > 4) return "[truncated]"
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
                endTimeUnixNano: String(
                  (event.createdAt + (event.durationMs ?? 0)) * 1_000_000,
                ),
                attributes: [
                  { key: "butler.kind", value: { stringValue: event.kind } },
                  { key: "butler.status", value: { stringValue: event.status } },
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
    readonly kind?: TraceKind
    readonly limit?: number
  },
): readonly TraceEvent[] {
  const limit = filter.limit ?? 100
  return events
    .filter((e) => (filter.runId ? e.runId === filter.runId : true))
    .filter((e) => (filter.conversationId ? e.conversationId === filter.conversationId : true))
    .filter((e) => (filter.kind ? e.kind === filter.kind : true))
    .slice(-Math.max(0, limit))
}
