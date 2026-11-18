import type { StoredMessage } from "@butler/domain/runtime.js"
import type { WorkingSetBudget } from "./working-set.js"

export type WorkingSetMode = "default" | "dev"

const DEFAULT_MAX_MESSAGES = 12
const DEFAULT_MAX_CHARS = 4000
const DEFAULT_DEV_MAX_MESSAGES = 20
const DEFAULT_DEV_MAX_CHARS = 8000

/** Short user turns dropped from dev history (except the last few turns). */
const DEV_HISTORY_NOISE_RE =
  /^(?:ping|pong|hi|hello|hey|你好|您好|在吗|在不在|几点了?|现在几点|几点钟|status|pwd|whoami|(?:运行?\s*)?(?:pwd|whoami|ping)\s*(?:命令|一下)?)$/iu

function intEnv(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = Number(env[key] ?? "")
  return Number.isFinite(raw) && raw > 0 ? Math.floor(raw) : fallback
}

export function resolveWorkingSetBudget(
  env: NodeJS.ProcessEnv = process.env,
  mode: WorkingSetMode = "default",
): WorkingSetBudget {
  if (mode === "dev") {
    return {
      maxMessages: intEnv(env, "BUTLER_V5_DEV_WORKING_SET_MAX_MESSAGES", DEFAULT_DEV_MAX_MESSAGES),
      maxChars: intEnv(env, "BUTLER_V5_DEV_WORKING_SET_MAX_CHARS", DEFAULT_DEV_MAX_CHARS),
    }
  }
  return {
    maxMessages: intEnv(env, "BUTLER_V5_WORKING_SET_MAX_MESSAGES", DEFAULT_MAX_MESSAGES),
    maxChars: intEnv(env, "BUTLER_V5_WORKING_SET_MAX_CHARS", DEFAULT_MAX_CHARS),
  }
}

export function workingSetModeFromTriggerPayload(
  payload: Readonly<Record<string, unknown>> | undefined,
): WorkingSetMode {
  if (payload?.["workingSetMode"] === "dev") return "dev"
  return "default"
}

function messageText(content: Readonly<Record<string, unknown>>): string {
  const text = content["text"]
  if (typeof text === "string") return text.trim()
  const body = content["body"]
  if (typeof body === "string") return body.trim()
  return ""
}

/**
 * Drop stale chat-only turns from dev working-set input so repeated ping/pwd
 * tests do not steer the plan model away from delegate/dev work.
 */
export function filterDevHistoryNoise(
  messages: readonly StoredMessage[],
  opts: { readonly keepTail?: number } = {},
): readonly StoredMessage[] {
  const keepTail = opts.keepTail ?? 4
  if (messages.length <= keepTail) return messages
  const head = messages.slice(0, -keepTail)
  const tail = messages.slice(-keepTail)
  const filteredHead = head.filter((message) => {
    if (message.role !== "user") return true
    const text = messageText(message.content)
    if (!text) return false
    return !DEV_HISTORY_NOISE_RE.test(text)
  })
  return [...filteredHead, ...tail]
}
