/**
 * Optional Flash LLM layer for WeChat intake intent classification.
 */
import { Effect } from "effect"
import { pickIntakeLLM, type LLMMessage } from "@butler/adapters"
import { envTruthy } from "./env-util.js"
import type { WechatIntent, WechatIntentKind } from "./wechat-intake.js"

const INTAKE_TIMEOUT = "6 seconds" as const

const VALID_KINDS: readonly WechatIntentKind[] = [
  "chat",
  "dev_task",
  "dev_session",
  "switch_project",
  "continue_dev",
]

function parseIntakeJson(text: string): WechatIntent | null {
  const trimmed = text.trim()
  const start = trimmed.indexOf("{")
  const end = trimmed.lastIndexOf("}")
  if (start < 0 || end <= start) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed.slice(start, end + 1))
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null
  const obj = parsed as Record<string, unknown>
  const kind = obj["kind"]
  if (typeof kind !== "string" || !VALID_KINDS.includes(kind as WechatIntentKind)) {
    return null
  }
  const intent: WechatIntent = { kind: kind as WechatIntentKind }
  if (typeof obj["goal"] === "string" && obj["goal"].trim()) {
    return { ...intent, goal: obj["goal"].trim() }
  }
  if (typeof obj["switchTarget"] === "string" && obj["switchTarget"].trim()) {
    return { ...intent, switchTarget: obj["switchTarget"].trim() }
  }
  return intent
}

export function isWechatIntakeLlmEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_INTAKE_LLM"])
}

/** When rules already picked a non-chat intent, LLM must not downgrade it. */
export function shouldSkipIntakeLlm(fallback: WechatIntent): boolean {
  return fallback.kind !== "chat"
}

export async function classifyWechatIntentWithLlm(args: {
  readonly content: string
  readonly fallback: WechatIntent
  readonly env?: NodeJS.ProcessEnv
}): Promise<{ readonly intent: WechatIntent; readonly source: "rules" | "llm" }> {
  const env = args.env ?? process.env
  if (!isWechatIntakeLlmEnabled(env)) {
    return { intent: args.fallback, source: "rules" }
  }
  if (shouldSkipIntakeLlm(args.fallback)) {
    return { intent: args.fallback, source: "rules" }
  }
  const adapter = pickIntakeLLM(env)
  if (!adapter) {
    return { intent: args.fallback, source: "rules" }
  }
  const messages: readonly LLMMessage[] = [
    {
      role: "system",
      content: [
        "You classify WeChat user messages for a butler agent.",
        "Return exactly one JSON object (no markdown):",
        '{ "kind": "chat"|"dev_task"|"dev_session"|"switch_project"|"continue_dev",',
        '  "goal"?: "...", "switchTarget"?: "..." }',
        "",
        "Rules:",
        "- dev_session: user wants dev mode / 开发模式",
        "- switch_project: user wants to switch project (切到/切换到 X)",
        "- dev_task: implement/fix/refactor/code change requests; messages naming write_file or run_command are always dev_task",
        "- continue_dev: continue previous dev work (继续/接着)",
        "- chat: greetings, questions, read-only, reminders, ping, time, status",
        "",
        "When unsure, use chat. Do not use dev_task for simple questions or ping.",
        "Never classify write_file / run_command literal tool requests as chat.",
      ].join("\n"),
    },
    { role: "user", content: args.content.trim() },
  ]
  const outcome = await Effect.runPromise(
    adapter.complete(messages).pipe(
      Effect.timeout(INTAKE_TIMEOUT),
      Effect.match({
        onFailure: () => ({ content: "" }),
        onSuccess: (resp) => resp,
      }),
    ),
  )
  const parsed = parseIntakeJson(outcome.content)
  if (!parsed) {
    return { intent: args.fallback, source: "rules" }
  }
  if (shouldSkipIntakeLlm(args.fallback) && parsed.kind === "chat") {
    return { intent: args.fallback, source: "rules" }
  }
  return { intent: parsed, source: "llm" }
}
