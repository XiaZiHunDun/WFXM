/**
 * In-process local tracer (ring buffer). Not an OpenTelemetry SDK.
 */
import {
  applyTraceRedaction,
  createTraceEvent,
  filterTraceEvents,
  formatOtelStdoutLine,
  parseTraceConfig,
  type CreateTraceEventInput,
  type TraceConfig,
  type TraceEvent,
  type TraceKind,
} from "@butler/domain/observability/local-trace.js"

export interface LocalTracer {
  readonly config: TraceConfig
  readonly record: (input: CreateTraceEventInput) => TraceEvent | null
  readonly list: (filter?: {
    readonly runId?: string
    readonly conversationId?: string
    readonly kind?: TraceKind
    readonly limit?: number
  }) => readonly TraceEvent[]
  readonly clear: () => void
  readonly size: () => number
}

export function createLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
  opts?: {
    readonly writeStdout?: (line: string) => void
  },
): LocalTracer {
  const config = parseTraceConfig(env)
  const buffer: TraceEvent[] = []
  const writeStdout = opts?.writeStdout ?? ((line: string) => {
    // eslint-disable-next-line no-console -- intentional opt-in exporter
    console.error(line)
  })

  return {
    config,
    record(input) {
      if (!config.enabled) return null
      const raw = createTraceEvent(input)
      const event = config.redact ? applyTraceRedaction(raw) : raw
      buffer.push(event)
      while (buffer.length > config.maxEvents) {
        buffer.shift()
      }
      if (config.exporter === "stdout") {
        try {
          writeStdout(formatOtelStdoutLine(event))
        } catch {
          // exporter must never break the run
        }
      }
      return event
    },
    list(filter = {}) {
      return filterTraceEvents(buffer, filter)
    },
    clear() {
      buffer.length = 0
    },
    size() {
      return buffer.length
    },
  }
}

let shared: LocalTracer | null = null

/** Process-wide tracer used by delivery shell (resettable in tests). */
export function getSharedLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
): LocalTracer {
  if (!shared) shared = createLocalTracer(env)
  return shared
}

export function resetSharedLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
): LocalTracer {
  shared = createLocalTracer(env)
  return shared
}
