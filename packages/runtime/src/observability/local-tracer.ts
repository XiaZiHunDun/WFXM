/**
 * In-process local tracer (ring buffer + optional async sink). Not an
 * OpenTelemetry SDK.
 *
 * Phase 5 P0: when a `sink` is configured, events are also queued and
 * written in batches (size / interval thresholds) so a mobile-narrow
 * deployment can persist traces without blocking the request path. Sink
 * failures are counted and dropped — the run must never fail because
 * trace persistence failed.
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

/** Batched async persistence boundary (TraceStore satisfies this). */
export interface TraceSink {
  readonly append: (events: readonly TraceEvent[]) => Promise<void>
}

export interface LocalTracerStats {
  /** Events successfully handed to the sink. */
  readonly written: number
  /** Events dropped because the sink threw. */
  readonly dropped: number
}

export interface LocalTracerOptions {
  readonly writeStdout?: (line: string) => void
  readonly sink?: TraceSink
  readonly batchSize?: number
  readonly flushIntervalMs?: number
}

export interface LocalTracer {
  readonly config: TraceConfig
  readonly record: (input: CreateTraceEventInput) => TraceEvent | null
  readonly list: (filter?: {
    readonly runId?: string
    readonly conversationId?: string
    readonly turnId?: string
    readonly kind?: TraceKind
    readonly limit?: number
  }) => readonly TraceEvent[]
  readonly clear: () => void
  readonly size: () => number
  /** Events queued for the sink but not yet written. */
  readonly pending: () => number
  readonly stats: () => LocalTracerStats
  /** Write all queued events now; never throws. */
  readonly flush: () => Promise<void>
  /** Stop the interval timer and flush remaining events. */
  readonly close: () => Promise<void>
}

function envPositiveInt(
  env: Readonly<Record<string, string | undefined>>,
  key: string,
  fallback: number,
): number {
  const raw = Number(env[key] ?? fallback)
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : fallback
}

export function createLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
  opts?: LocalTracerOptions,
): LocalTracer {
  const config = parseTraceConfig(env)
  const buffer: TraceEvent[] = []
  const writeStdout =
    opts?.writeStdout ??
    ((line: string) => {
      // eslint-disable-next-line no-console -- intentional opt-in exporter
      console.error(line)
    })
  const sink = opts?.sink
  const batchSize = opts?.batchSize ?? envPositiveInt(env, "BUTLER_V5_TRACE_BATCH_SIZE", 50)
  const flushIntervalMs =
    opts?.flushIntervalMs ?? envPositiveInt(env, "BUTLER_V5_TRACE_FLUSH_MS", 2000)

  const queue: TraceEvent[] = []
  let timer: ReturnType<typeof setInterval> | null = null
  let inflight: Promise<void> | null = null
  let written = 0
  let dropped = 0

  const flushBatch = async (): Promise<void> => {
    if (inflight) await inflight
    while (sink && queue.length > 0) {
      const batch = queue.splice(0, queue.length)
      const run = (async (): Promise<void> => {
        try {
          await sink.append(batch)
          written += batch.length
        } catch (err) {
          dropped += batch.length
          // eslint-disable-next-line no-console -- trace persistence must not break the run
          console.error("[local-tracer] sink append failed; dropping batch:", err)
        }
      })()
      inflight = run
      try {
        await run
      } finally {
        inflight = null
      }
    }
  }

  if (sink && config.enabled) {
    timer = setInterval(() => {
      void flushBatch()
    }, flushIntervalMs)
    // Never keep the process alive just for trace flushing.
    if (typeof timer.unref === "function") timer.unref()
  }

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
      if (sink) {
        queue.push(event)
        if (queue.length >= batchSize) {
          void flushBatch()
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
    pending() {
      return queue.length
    },
    stats() {
      return { written, dropped }
    },
    flush: flushBatch,
    async close() {
      if (timer !== null) {
        clearInterval(timer)
        timer = null
      }
      await flushBatch()
    },
  }
}

let shared: LocalTracer | null = null
let sharedOptions: LocalTracerOptions | undefined

/** Process-wide tracer used by delivery shell (resettable in tests). */
export function getSharedLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
): LocalTracer {
  if (!shared) shared = createLocalTracer(env, sharedOptions)
  return shared
}

/**
 * Replace the process-wide tracer. Previous instance is closed (its
 * interval timer cleared + queue flushed). When `opts` is omitted the
 * last configured options (notably `sink`) are reused — e.g. the owner
 * "clear traces" route must not silently drop the persistence sink.
 */
export function resetSharedLocalTracer(
  env: Readonly<Record<string, string | undefined>> = process.env,
  opts?: LocalTracerOptions,
): LocalTracer {
  if (shared) {
    const previous = shared
    void previous.close()
  }
  if (opts !== undefined) sharedOptions = opts
  shared = createLocalTracer(env, sharedOptions)
  return shared
}
