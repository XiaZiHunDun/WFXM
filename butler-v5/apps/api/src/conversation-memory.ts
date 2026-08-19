/**
 * R8.x.13 — multi-turn conversation memory.
 *
 * Turns the event stream into LLM messages (user / assistant) and
 * compact older turns into a short extractive summary so the context
 * window stays bounded. No extra LLM call.
 */
import type { LLMMessage } from "@butler/adapters"

export interface HistoryEvent {
  readonly eventType: string
  readonly payload: unknown
}

export interface CompactOptions {
  readonly maxMessages?: number
  readonly maxChars?: number
}

export interface CompactResult {
  readonly messages: readonly LLMMessage[]
  readonly compacted: boolean
}

const DEFAULT_MAX_MESSAGES = 12
const DEFAULT_MAX_CHARS = 4000
const SUMMARY_LINE_MAX = 80

function payloadContent(payload: unknown): string {
  if (payload === null || typeof payload !== "object") return ""
  const content = (payload as { content?: unknown }).content
  return typeof content === "string" ? content.trim() : ""
}

function payloadRole(payload: unknown): string {
  if (payload === null || typeof payload !== "object") return ""
  const role = (payload as { role?: unknown }).role
  return typeof role === "string" ? role : ""
}

/**
 * Convert stored conversation events into chat turns.
 * `ConversationStarted` is skipped (duplicates TurnOpened from the route).
 * When `currentUserContent` is set, a trailing user turn with that
 * text is dropped so the inbound loop can append it once.
 */
export function eventsToHistoryMessages(
  events: readonly HistoryEvent[],
  opts: { readonly currentUserContent?: string } = {},
): readonly LLMMessage[] {
  const out: LLMMessage[] = []
  for (const e of events) {
    const content = payloadContent(e.payload)
    if (!content) continue
    if (e.eventType === "TurnOpened" && payloadRole(e.payload) !== "assistant") {
      out.push({ role: "user", content })
      continue
    }
    if (e.eventType === "AssistantMessageProduced") {
      out.push({ role: "assistant", content })
    }
  }
  const current = opts.currentUserContent?.trim()
  if (current && out.length > 0) {
    const last = out[out.length - 1]
    if (last?.role === "user" && last.content === current) {
      return out.slice(0, -1)
    }
  }
  return out
}

/**
 * Keep the newest turns that fit the budget. Dropped older turns become
 * one system summary message prepended to the kept list.
 */
export function compactConversationHistory(
  messages: readonly LLMMessage[],
  opts: CompactOptions = {},
): CompactResult {
  const maxMessages = opts.maxMessages ?? DEFAULT_MAX_MESSAGES
  const maxChars = opts.maxChars ?? DEFAULT_MAX_CHARS
  if (messages.length === 0) {
    return { messages: [], compacted: false }
  }

  const kept: LLMMessage[] = []
  let chars = 0
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (!msg) continue
    if (kept.length >= maxMessages) break
    const nextChars = chars + msg.content.length
    if (kept.length > 0 && nextChars > maxChars) break
    kept.unshift(msg)
    chars = nextChars
  }

  const droppedCount = messages.length - kept.length
  if (droppedCount <= 0) {
    return { messages: kept, compacted: false }
  }

  const dropped = messages.slice(0, droppedCount)
  const lines = dropped.map((m) => {
    const body =
      m.content.length <= SUMMARY_LINE_MAX
        ? m.content
        : `${m.content.slice(0, SUMMARY_LINE_MAX - 3)}...`
    return `- ${m.role}: ${body}`
  })
  const summary: LLMMessage = {
    role: "system",
    content: `Earlier conversation (summarized, oldest first):\n${lines.join("\n")}`,
  }
  return { messages: [summary, ...kept], compacted: true }
}
