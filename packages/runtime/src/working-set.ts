import type { StoredMessage, StoredStep } from "@butler/domain/runtime.js"

export interface WorkingSetMessage {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string
}

export interface WorkingSetBudget {
  readonly maxMessages?: number
  readonly maxChars?: number
}

export interface WorkingSetInput {
  readonly systemPrefix?: readonly WorkingSetMessage[]
  readonly messages: readonly StoredMessage[]
  readonly currentRunSteps?: readonly StoredStep[]
  readonly trailingUserContent?: string
  readonly budget?: WorkingSetBudget
}

export interface WorkingSetResult {
  readonly messages: readonly WorkingSetMessage[]
  readonly compacted: boolean
  readonly source: "none" | "extractive"
  readonly droppedCount: number
}

const DEFAULT_MAX_MESSAGES = 12
const DEFAULT_MAX_CHARS = 4000
const SUMMARY_LINE_MAX = 80
const TOOL_REF_MAX = 120

function messageContent(content: Readonly<Record<string, unknown>>): string {
  const text = content["text"]
  if (typeof text === "string") return text.trim()
  const body = content["body"]
  if (typeof body === "string") return body.trim()
  return JSON.stringify(content)
}

function storedToLlm(message: StoredMessage): WorkingSetMessage {
  const content = messageContent(message.content)
  if (message.role === "tool") {
    const ref = content.length > TOOL_REF_MAX ? `${content.slice(0, TOOL_REF_MAX - 3)}...` : content
    return {
      role: "tool",
      content: `[tool-result-ref:${message.id}] ${ref}`,
    }
  }
  return { role: message.role, content }
}

function stepToLlm(step: StoredStep): WorkingSetMessage | null {
  if (step.kind !== "capability" && step.kind !== "model") return null
  const raw =
    step.output !== null
      ? JSON.stringify(step.output)
      : step.input["prompt"] !== undefined
        ? String(step.input["prompt"])
        : JSON.stringify(step.input)
  const body = raw.length > TOOL_REF_MAX ? `${raw.slice(0, TOOL_REF_MAX - 3)}...` : raw
  return {
    role: "system",
    content: `[run-step:${step.id}] ${step.kind}/${step.status}: ${body}`,
  }
}

function splitBudget(
  messages: readonly WorkingSetMessage[],
  budget: WorkingSetBudget,
): { readonly kept: readonly WorkingSetMessage[]; readonly dropped: readonly WorkingSetMessage[] } {
  const maxMessages = budget.maxMessages ?? DEFAULT_MAX_MESSAGES
  const maxChars = budget.maxChars ?? DEFAULT_MAX_CHARS
  const kept: WorkingSetMessage[] = []
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

function extractiveSummary(dropped: readonly WorkingSetMessage[]): WorkingSetMessage {
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

/** Build a budgeted working set for model input without deleting stored history. */
export function buildWorkingSet(input: WorkingSetInput): WorkingSetResult {
  const history = input.messages.map(storedToLlm).filter((m) => m.content.length > 0)
  const trailing = input.trailingUserContent?.trim()
  const trimmedHistory =
    trailing && history.length > 0
      ? (() => {
          const last = history[history.length - 1]
          if (last?.role === "user" && last.content === trailing) {
            return history.slice(0, -1)
          }
          return history
        })()
      : history

  const stepMessages = (input.currentRunSteps ?? [])
    .map(stepToLlm)
    .filter((m): m is WorkingSetMessage => m !== null)

  const combined = [...trimmedHistory, ...stepMessages]
  if (combined.length === 0) {
    const prefix = input.systemPrefix ?? []
    const trailingMsg = trailing ? [{ role: "user" as const, content: trailing }] : []
    return {
      messages: [...prefix, ...trailingMsg],
      compacted: false,
      source: "none",
      droppedCount: 0,
    }
  }

  const { kept, dropped } = splitBudget(combined, input.budget ?? {})
  const prefix = input.systemPrefix ?? []
  const trailingMsg = trailing ? [{ role: "user" as const, content: trailing }] : []

  if (dropped.length === 0) {
    return {
      messages: [...prefix, ...kept, ...trailingMsg],
      compacted: false,
      source: "none",
      droppedCount: 0,
    }
  }

  return {
    messages: [...prefix, extractiveSummary(dropped), ...kept, ...trailingMsg],
    compacted: true,
    source: "extractive",
    droppedCount: dropped.length,
  }
}
