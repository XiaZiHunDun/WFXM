import type { Hono } from "hono"
import type { TraceEvent } from "@butler/domain/observability/local-trace.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import type { Wiring } from "../wiring.js"
import { ownerAuthorized } from "../owner-auth.js"

/**
 * Per-conversation usage breakdown. `capabilityCalls` is a name → count
 * map so the owner UI can show which capabilities dominated a run.
 * Tokens/cost come from llm_call step events (D23/D24 trace payload).
 */
export interface ConversationUsage {
  readonly llmCalls: number
  readonly inputTokens: number
  readonly outputTokens: number
  readonly totalTokens: number
  readonly costUsd: number
  readonly capabilityCalls: Readonly<Record<string, number>>
}

/**
 * Aggregate across all conversations in the queried window.
 * `capabilityCalls` is the integer count (not a map) so the owner
 * dashboard can render a single total tile without re-summing the map.
 */
export interface UsageTotals {
  readonly llmCalls: number
  readonly inputTokens: number
  readonly outputTokens: number
  readonly totalTokens: number
  readonly costUsd: number
  readonly capabilityCalls: number
}

export interface UsageAggregate {
  readonly totals: UsageTotals
  readonly conversations: Readonly<Record<string, ConversationUsage>>
}

const UNSCOPED = "_unscoped"

// Mutable internal accumulator shape — the public types above are
// readonly. We mutate during the fold and cast at the return boundary.
interface MutableConversation {
  llmCalls: number
  inputTokens: number
  outputTokens: number
  totalTokens: number
  costUsd: number
  capabilityCalls: Record<string, number>
}

interface MutableTotals {
  llmCalls: number
  inputTokens: number
  outputTokens: number
  totalTokens: number
  costUsd: number
  capabilityCalls: number
}

function emptyConversation(): MutableConversation {
  return {
    llmCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
    capabilityCalls: {},
  }
}

function emptyTotals(): MutableTotals {
  return {
    llmCalls: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
    capabilityCalls: 0,
  }
}

/**
 * Pure aggregator. Buckets llm_call step events (counts + tokens + cost)
 * and capability events (counts by name per conversation, integer total
 * across conversations) per conversationId. Events with no
 * conversationId bucket under `_unscoped`. Non-llm_call step events
 * are ignored.
 */
export function aggregateUsage(events: readonly TraceEvent[]): UsageAggregate {
  const totals: MutableTotals = emptyTotals()
  const conversations: Record<string, MutableConversation> = {}

  const slotFor = (id: string): MutableConversation => {
    let s = conversations[id]
    if (!s) {
      s = emptyConversation()
      conversations[id] = s
    }
    return s
  }

  for (const e of events) {
    const convId = e.conversationId ?? UNSCOPED
    const slot = slotFor(convId)

    if (e.kind === "step" && e.name === "llm_call") {
      slot.llmCalls += 1
      totals.llmCalls += 1
      if (e.token) {
        slot.inputTokens += e.token.inputTokens
        slot.outputTokens += e.token.outputTokens
        slot.totalTokens += e.token.totalTokens
        totals.inputTokens += e.token.inputTokens
        totals.outputTokens += e.token.outputTokens
        totals.totalTokens += e.token.totalTokens
      }
      if (e.costUsd !== null && e.costUsd !== undefined) {
        slot.costUsd += e.costUsd
        totals.costUsd += e.costUsd
      }
    } else if (e.kind === "capability") {
      const name = e.name
      slot.capabilityCalls = {
        ...slot.capabilityCalls,
        [name]: (slot.capabilityCalls[name] ?? 0) + 1,
      }
      totals.capabilityCalls += 1
    }
  }

  return {
    totals: totals as UsageTotals,
    conversations: conversations as Record<string, ConversationUsage>,
  }
}

/**
 * Owner GET /v1/owner/usage?conversationId=&limit=
 *
 * Returns the trace-bucket aggregate. `conversationId` is optional; when
 * present, only events for that conversation are aggregated. `limit`
 * defaults to 5000 (matches the upstream `tracer.list` default cap).
 */
export function registerUsageRoutes(app: Hono, _wiring: Wiring): void {
  app.get("/v1/owner/usage", async (c) => {
    if (!ownerAuthorized(c)) return c.text("unauthorized", 401)
    const tracer = getSharedLocalTracer()
    const conversationId = c.req.query("conversationId")?.trim() || undefined
    const limitRaw = Number(c.req.query("limit") ?? 5000)
    const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? Math.floor(limitRaw) : 5000
    const events = tracer.list({
      ...(conversationId ? { conversationId } : {}),
      limit,
    })
    const agg = aggregateUsage(events)
    return c.json({
      enabled: tracer.config.enabled,
      totals: agg.totals,
      conversations: agg.conversations,
    })
  })
}
