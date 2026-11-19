/**
 * P4.1 model layer: pi-ai -> custom OpenAI-compatible endpoint (MiniMax).
 *
 * Uses non-streaming `completeSimple` wrapped in pi's assistant event stream.
 * `retryAssistantCall` owns 429/5xx retries so the task runner does not need a
 * second retry loop.
 */
import type { StreamFn } from "@butler/pi-agent"
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai/utils/event-stream"
import { retryAssistantCall } from "@earendil-works/pi-ai/utils/retry"
import type { AssistantMessage, Model } from "@earendil-works/pi-ai"
import { completeSimple } from "@earendil-works/pi-ai/compat"

export interface PiModelConfig {
  readonly model: Model<"openai-completions">
  readonly apiKey: string
}

function envTrim(env: NodeJS.ProcessEnv, key: string): string {
  return (env[key] ?? "").trim()
}

function positiveInt(raw: string, fallback: number): number {
  const parsed = Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback
}

/** Resolve the task-layer model from the same env keys the butler uses. */
export function resolvePiModelFromEnv(env: NodeJS.ProcessEnv = process.env): PiModelConfig {
  const baseUrl = envTrim(env, "MINIMAX_BASE_URL")
  const apiKey = envTrim(env, "MINIMAX_CN_API_KEY") || envTrim(env, "MINIMAX_API_KEY")
  if (!baseUrl) throw new Error("MINIMAX_BASE_URL is required for the pi task layer")
  if (!apiKey) {
    throw new Error("MINIMAX_CN_API_KEY or MINIMAX_API_KEY is required for the pi task layer")
  }

  const model: Model<"openai-completions"> = {
    id: envTrim(env, "MINIMAX_MODEL") || "MiniMax-M3.1-Flash",
    name: "minimax",
    api: "openai-completions",
    provider: "minimax",
    baseUrl,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 128_000,
    maxTokens: positiveInt(envTrim(env, "BUTLER_V5_PI_MAX_TOKENS"), 8_192),
    reasoning: false,
  }
  return { model, apiKey }
}

export interface PiStreamFnOptions {
  readonly model: Model<"openai-completions">
  readonly apiKey: string
  readonly temperature?: number
  readonly maxRetries?: number
  readonly baseDelayMs?: number
}

/** Wrap `completeSimple` in a pi stream so the vendored Agent can consume it. */
export function createPiStreamFn(input: PiStreamFnOptions): StreamFn {
  const temperature = input.temperature ?? 0
  const maxRetries = input.maxRetries ?? 3
  const baseDelayMs = input.baseDelayMs ?? 1_000

  return (_model, context, options) => {
    const stream = createAssistantMessageEventStream()
    void (async () => {
      try {
        const message = await retryAssistantCall(
          () =>
            completeSimple(input.model, context, {
              apiKey: input.apiKey,
              temperature,
              maxTokens: input.model.maxTokens,
              signal: options?.signal,
            }),
          { enabled: maxRetries > 0, maxRetries, baseDelayMs },
          options?.signal,
        )
        emitAssistant(stream, message)
      } catch (error) {
        const message: AssistantMessage = {
          role: "assistant",
          content: [],
          api: input.model.api,
          provider: input.model.provider,
          model: input.model.id,
          usage: {
            input: 0,
            output: 0,
            cacheRead: 0,
            cacheWrite: 0,
            totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
          },
          stopReason: "error",
          errorMessage: error instanceof Error ? error.message : String(error),
          timestamp: Date.now(),
        }
        stream.push({ type: "error", reason: "error", error: message })
      }
    })()
    return stream
  }
}

type AssistantStream = ReturnType<typeof createAssistantMessageEventStream>

function emitAssistant(stream: AssistantStream, message: AssistantMessage): void {
  stream.push({ type: "start", partial: message })

  let contentIndex = 0
  for (const block of message.content) {
    if (block.type !== "text") continue
    stream.push({ type: "text_start", contentIndex, partial: message })
    stream.push({ type: "text_delta", contentIndex, delta: block.text, partial: message })
    stream.push({ type: "text_end", contentIndex, content: block.text, partial: message })
    contentIndex += 1
  }

  if (message.stopReason === "error") {
    stream.push({ type: "error", reason: "error", error: message })
    return
  }
  stream.push({
    type: "done",
    reason: message.stopReason === "toolUse" ? "toolUse" : "stop",
    message,
  })
}
