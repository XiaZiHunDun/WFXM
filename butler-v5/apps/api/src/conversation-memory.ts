/**
 * R8.x.13 / R8.x.14 — multi-turn conversation memory.
 *
 * Turns the event stream into LLM messages (user / assistant) and
 * compact older turns. Default compact is extractive; when an LLM
 * adapter is provided, dropped turns are summarized by the model
 * with extractive fallback.
 */
import { Effect } from "effect"
import type { LLMAdapter, LLMMessage } from "@butler/adapters"

export interface HistoryEvent {
  readonly eventType: string
  readonly payload: unknown
}

export interface CompactOptions {
  readonly maxMessages?: number
  readonly maxChars?: number
}

export type CompactSource = "none" | "extractive" | "llm"

export interface CompactResult {
  readonly messages: readonly LLMMessage[]
  readonly compacted: boolean
  readonly source: CompactSource
}

const DEFAULT_MAX_MESSAGES = 12
const DEFAULT_MAX_CHARS = 4000
const SUMMARY_LINE_MAX = 80
const SUMMARIZER_TIMEOUT = "8 seconds" as const
const SUMMARIZER_INPUT_MAX = 6000

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

function splitBudget(
  messages: readonly LLMMessage[],
  opts: CompactOptions,
): { readonly kept: readonly LLMMessage[]; readonly dropped: readonly LLMMessage[] } {
  const maxMessages = opts.maxMessages ?? DEFAULT_MAX_MESSAGES
  const maxChars = opts.maxChars ?? DEFAULT_MAX_CHARS
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
  return {
    kept,
    dropped: droppedCount > 0 ? messages.slice(0, droppedCount) : [],
  }
}

function extractiveSummaryMessage(dropped: readonly LLMMessage[]): LLMMessage {
  const lines = dropped.map((m) => {
    const body =
      m.content.length <= SUMMARY_LINE_MAX
        ? m.content
        : `${m.content.slice(0, SUMMARY_LINE_MAX - 3)}...`
    return `- ${m.role}: ${body}`
  })
  return {
    role: "system",
    content: `Earlier conversation (summarized, oldest first):\n${lines.join("\n")}`,
  }
}

/**
 * Keep the newest turns that fit the budget. Dropped older turns become
 * one extractive system summary message prepended to the kept list.
 */
export function compactConversationHistory(
  messages: readonly LLMMessage[],
  opts: CompactOptions = {},
): CompactResult {
  if (messages.length === 0) {
    return { messages: [], compacted: false, source: "none" }
  }
  const { kept, dropped } = splitBudget(messages, opts)
  if (dropped.length === 0) {
    return { messages: kept, compacted: false, source: "none" }
  }
  return {
    messages: [extractiveSummaryMessage(dropped), ...kept],
    compacted: true,
    source: "extractive",
  }
}

function droppedTranscript(dropped: readonly LLMMessage[]): string {
  const raw = dropped.map((m) => `${m.role}: ${m.content}`).join("\n")
  if (raw.length <= SUMMARIZER_INPUT_MAX) return raw
  return `${raw.slice(0, SUMMARIZER_INPUT_MAX - 3)}...`
}

async function llmSummarizeDropped(
  adapter: LLMAdapter,
  dropped: readonly LLMMessage[],
): Promise<string | undefined> {
  const transcript = droppedTranscript(dropped)
  const messages: LLMMessage[] = [
    {
      role: "system",
      content:
        "你是对话摘要器。把较早的对话压成不超过 8 句的中文要点，保留人名、偏好、未完成约定。只输出摘要，不要对用户说话。",
    },
    { role: "user", content: transcript },
  ]
  const outcome = await Effect.runPromise(
    adapter.complete(messages).pipe(
      Effect.timeout(SUMMARIZER_TIMEOUT),
      Effect.match({
        onFailure: () => ({ ok: false as const }),
        onSuccess: (resp) => ({ ok: true as const, text: resp.content.trim() }),
      }),
    ),
  )
  if (!outcome.ok || !outcome.text) return undefined
  return outcome.text
}

/**
 * Same split as extractive compact, but summarize dropped turns with
 * the LLM when provided. On timeout/empty/error, fall back to extractive.
 */
export async function compactConversationHistoryWithLlm(
  messages: readonly LLMMessage[],
  opts: CompactOptions & { readonly adapter?: LLMAdapter } = {},
): Promise<CompactResult> {
  if (messages.length === 0) {
    return { messages: [], compacted: false, source: "none" }
  }
  const { kept, dropped } = splitBudget(messages, opts)
  if (dropped.length === 0) {
    return { messages: kept, compacted: false, source: "none" }
  }
  if (opts.adapter) {
    const text = await llmSummarizeDropped(opts.adapter, dropped)
    if (text) {
      return {
        messages: [{ role: "system", content: `Earlier conversation summary:\n${text}` }, ...kept],
        compacted: true,
        source: "llm",
      }
    }
  }
  return {
    messages: [extractiveSummaryMessage(dropped), ...kept],
    compacted: true,
    source: "extractive",
  }
}
