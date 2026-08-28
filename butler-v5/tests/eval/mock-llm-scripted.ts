/**
 * Scripted mock LLM adapter — extends the pattern in apps/api/src/wechat-inbound-butler.test.ts
 * with introspection (call counters + per-call latency) and controllable failure.
 * Per-call responses are popped FIFO; if exhausted, returns an empty text response.
 */
import { Effect } from "effect"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"

export interface ScriptedLLMConfig {
  readonly responses: readonly LLMAssistantResponse[]
  /** Inject latency per call (ms). Useful for exercising slow-LLM code paths. */
  readonly latencyMs?: number
  /** Make the N-th call (1-indexed) fail with `failMessage`. 0 means no failures. */
  readonly failOnCall?: number
  readonly failMessage?: string
}

export interface ScriptedLLMCall {
  readonly messagesCount: number
  readonly toolsCount: number
}

export interface ScriptedLLMHandle {
  readonly adapter: LLMAdapter
  readonly callCount: () => number
  readonly getCalls: () => readonly ScriptedLLMCall[]
  readonly latencyByCall: () => readonly number[]
}

export function makeScriptedAdapter(config: ScriptedLLMConfig): ScriptedLLMHandle {
  let callIndex = 0
  const calls: ScriptedLLMCall[] = []
  const latencies: number[] = []
  const latency = config.latencyMs ?? 0
  const failOn = config.failOnCall ?? 0
  const failMsg = config.failMessage ?? "simulated LLM failure"
  const adapter: LLMAdapter = {
    complete: (messages, opts) => {
      const t0 = Date.now()
      const idx = callIndex++
      calls.push({
        messagesCount: messages.length,
        toolsCount: (opts?.tools ?? []).length,
      })
      const reply = config.responses[idx] ?? {
        content: "",
        toolCalls: [],
        stopReason: "stop",
      }
      latencies.push(Date.now() - t0)
      // Latency injection uses Effect's sleep to keep the contract synchronous to the caller.
      const sleep =
        latency > 0
          ? Effect.tryPromise({
              try: () => new Promise<void>((r) => setTimeout(r, latency)),
              catch: (e) => (e instanceof Error ? e : new Error(String(e))),
            })
          : Effect.succeed(undefined)
      return sleep.pipe(
        Effect.flatMap(() =>
          failOn > 0 && idx === failOn ? Effect.fail(new Error(failMsg)) : Effect.succeed(reply),
        ),
      )
    },
  }
  return {
    adapter,
    callCount: () => callIndex,
    getCalls: () => calls.slice(),
    latencyByCall: () => latencies.slice(),
  }
}

/** Build a text-only assistant response (used for JSON-decision turns). */
export function textResponse(content: string): LLMAssistantResponse {
  return { content, toolCalls: [], stopReason: "end_turn" }
}

/** Build a native tool_call response. */
export function toolCallResponse(
  toolCalls: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[],
  content = "",
): LLMAssistantResponse {
  return { content, toolCalls, stopReason: "tool_use" }
}

/** Convenience: encode a Domain `ModelDecision` JSON payload as a text response. */
export function decisionResponse(decision: Record<string, unknown>): LLMAssistantResponse {
  return textResponse(JSON.stringify(decision))
}
