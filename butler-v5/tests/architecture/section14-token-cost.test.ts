/**
 * Arch guard (D23-arch-align §14 token/cost LLM-usage tracking): closes
 * the D21 "token/cost 真缺" gap by plumbing usage from the LLM boundary
 * into first-class `TraceEvent.token` (and reserved `TraceEvent.costUsd`).
 *
 * Plumbing chain that this guard locks:
 *   1. `LLMAssistantResponse.usage?` (provider-agnostic token shape) is
 *      declared on the LLM boundary (`packages/adapters/src/llm-provider.ts`).
 *   2. `anthropic.ts` parses `usage.input_tokens` / `usage.output_tokens`
 *      into `LLMUsage` (`inputTokens` / `outputTokens` / `totalTokens`).
 *   3. `openai-compatible.ts` parses `usage.prompt_tokens` /
 *      `usage.completion_tokens` / `usage.total_tokens` into `LLMUsage`.
 *   4. `ConversationLoopPorts.complete` return shape carries `usage?`
 *      so the loop gets token info from the caller.
 *   5. The 3 ports.complete callers that drive `runConversationLoop`
 *      (`wechat-inbound-butler.ts`, `subagent-worker.ts`,
 *      `approval-resume.ts`) forward `resp.usage` into the loop response
 *      AND emit `tracer.record({kind: "step", name: "llm_call", token})`
 *      so the §14 `token` field lands first-class in trace events.
 *   6. `TraceEvent` + `CreateTraceEventInput` declare first-class `token`
 *      and `costUsd`; `createTraceEvent` propagates them; `formatOtelStdoutLine`
 *      emits OTLP `butler.token.*` + `butler.costUsd` attributes.
 *
 * Static checks (no runtime):
 *   - llm-provider.ts declares `LLMUsage` interface and `LLMAssistantResponse.usage?`
 *   - anthropic.ts parses `usage` (input_tokens + output_tokens → LLMUsage)
 *   - openai-compatible.ts parses `usage` (prompt_tokens + completion_tokens)
 *   - conversation-loop.ts `ConversationLoopPorts.complete` response has `usage?`
 *   - 3 caller files contain `tracer.record({ kind: "step", name: "llm_call" ... token ... })`
 *   - local-trace.ts TraceEvent declares `token: TraceTokenUsage | null` and
 *     `costUsd: number | null`; `createTraceEvent` passes them through;
 *     `formatOtelStdoutLine` emits the OTLP attributes.
 *
 * Runtime behavior is verified by:
 *   - The 3 caller-side usage forwarding paths keep their existing
 *     happy-path eval scenarios green (eval/01..22 + tests/architecture
 *     gates).
 *   - tests/architecture/section14-observability-fields.test.ts (D21 +
 *     D23 update) declares `token` + `costUsd` as required top-level
 *     fields on `TraceEvent` + `CreateTraceEventInput`.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const LLM_PROVIDER = join(__dirname, "../../packages/adapters/src/llm-provider.ts")
const ANTHROPIC_ADAPTER = join(__dirname, "../../packages/adapters/src/llm/anthropic.ts")
const OPENAI_COMPAT_ADAPTER = join(__dirname, "../../packages/adapters/src/llm/openai-compatible.ts")
const CONVERSATION_LOOP = join(
  __dirname,
  "../../packages/runtime/src/execution/conversation-loop.ts",
)
const LOCAL_TRACE = join(
  __dirname,
  "../../packages/domain/src/observability/local-trace.ts",
)
const WECHAT_INBOUND_BUTLER = join(__dirname, "../../apps/api/src/wechat-inbound-butler.ts")
const SUBAGENT_WORKER = join(__dirname, "../../apps/api/src/subagent-worker.ts")
const APPROVAL_RESUME = join(__dirname, "../../apps/api/src/approval-resume.ts")

describe("arch: §14 token/cost LLM-usage tracking (D23 — D21 gap closed)", () => {
  // ── 1. LLM boundary declares usage? ──────────────────────────

  it("LLMAssistantResponse declares optional usage (provider-agnostic LLMUsage)", () => {
    const src = readFileSync(LLM_PROVIDER, "utf-8")
    expect(src).toMatch(/export\s+interface\s+LLMUsage\s*\{/)
    expect(src).toMatch(/readonly\s+inputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+outputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+totalTokens:\s*number/)
    expect(src).toMatch(
      /export\s+interface\s+LLMAssistantResponse\s*\{[\s\S]*?readonly\s+usage\?:\s*LLMUsage/s,
    )
  })

  // ── 2. Anthropic adapter parses upstream usage ───────────────

  it("anthropic adapter parses AnthropicResponse.usage into LLMUsage", () => {
    const src = readFileSync(ANTHROPIC_ADAPTER, "utf-8")
    // AnthropicResponse carries input_tokens + output_tokens.
    expect(src).toMatch(/input_tokens:\s*number/)
    expect(src).toMatch(/output_tokens:\s*number/)
    // parseAnthropicResponse normalizes to LLMUsage with totalTokens.
    expect(src).toMatch(/inputTokens:\s*data\.usage\.input_tokens/)
    expect(src).toMatch(/outputTokens:\s*data\.usage\.output_tokens/)
    expect(src).toMatch(/totalTokens:\s*data\.usage\.input_tokens\s*\+\s*data\.usage\.output_tokens/)
    // parseAnthropicResponse attaches usage via conditional spread.
    expect(src).toMatch(/\.\.\.\(usage\s*!==\s*undefined\s*\?\s*\{\s*usage\s*\}\s*:\s*\{\}\)/)
  })

  // ── 3. OpenAI-compatible adapter parses upstream usage ───────

  it("openai-compatible adapter parses OpenAIResponse.usage into LLMUsage", () => {
    const src = readFileSync(OPENAI_COMPAT_ADAPTER, "utf-8")
    expect(src).toMatch(/prompt_tokens:\s*number/)
    expect(src).toMatch(/completion_tokens:\s*number/)
    expect(src).toMatch(/total_tokens:\s*number/)
    // mapOpenAIUsage normalizes into LLMUsage.
    expect(src).toMatch(/inputTokens:\s*raw\.prompt_tokens/)
    expect(src).toMatch(/outputTokens:\s*raw\.completion_tokens/)
    expect(src).toMatch(/totalTokens:\s*raw\.total_tokens/)
    // parseOpenAIResponse attaches usage via conditional spread.
    expect(src).toMatch(/usage:\s*mapOpenAIUsage\(data\.usage\)/)
  })

  // ── 4. ConversationLoopPorts.complete returns usage? ─────────

  it("ConversationLoopPorts.complete return shape carries optional usage", () => {
    const src = readFileSync(CONVERSATION_LOOP, "utf-8")
    expect(src).toMatch(/readonly\s+usage\?:\s*\{/)
    expect(src).toMatch(/readonly\s+inputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+outputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+totalTokens:\s*number/)
  })

  // ── 5. Caller forwards usage + emits step/llm_call trace ─────

  it("wechat-inbound-butler forwards resp.usage and emits step/llm_call trace with token", () => {
    const src = readFileSync(WECHAT_INBOUND_BUTLER, "utf-8")
    // Forwards usage into the loop response shape.
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*usage:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
    // Emits llm_call step trace in both onSuccess and onFailure branches.
    expect(src).toMatch(/kind:\s*"step",\s*\n\s*name:\s*"llm_call"/)
    // Carries token first-class on success.
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*token:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
  })

  it("subagent-worker forwards resp.usage and emits step/llm_call trace with token", () => {
    const src = readFileSync(SUBAGENT_WORKER, "utf-8")
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*usage:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
    expect(src).toMatch(/kind:\s*"step",\s*\n\s*name:\s*"llm_call"/)
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*token:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
  })

  it("approval-resume forwards resp.usage and emits step/llm_call trace with token", () => {
    const src = readFileSync(APPROVAL_RESUME, "utf-8")
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*usage:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
    expect(src).toMatch(/kind:\s*"step",\s*\n\s*name:\s*"llm_call"/)
    expect(src).toMatch(/\.\.\.\(resp\.usage\s*!==\s*undefined\s*\?\s*\{\s*token:\s*resp\.usage\s*\}\s*:\s*\{\}\)/)
  })

  // ── 6. TraceEvent first-class token + costUsd + OTLP emit ────

  it("TraceEvent declares first-class token (TraceTokenUsage | null) + costUsd (number | null)", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    // TraceTokenUsage interface.
    expect(src).toMatch(/export\s+interface\s+TraceTokenUsage\s*\{/)
    expect(src).toMatch(/readonly\s+inputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+outputTokens:\s*number/)
    expect(src).toMatch(/readonly\s+totalTokens:\s*number/)
    // TraceEvent fields.
    const traceEventMatch = src.match(
      /export interface TraceEvent\s*\{([\s\S]*?)\n\}/,
    )
    expect(traceEventMatch, "TraceEvent interface not found").not.toBeNull()
    const body = traceEventMatch?.[1] ?? ""
    expect(body).toMatch(/readonly\s+token:\s*TraceTokenUsage\s*\|\s*null/)
    expect(body).toMatch(/readonly\s+costUsd:\s*number\s*\|\s*null/)
    // CreateTraceEventInput carries the same fields.
    const inputMatch = src.match(
      /export interface CreateTraceEventInput\s*\{([\s\S]*?)\n\}/,
    )
    expect(inputMatch, "CreateTraceEventInput interface not found").not.toBeNull()
    const inputBody = inputMatch?.[1] ?? ""
    expect(inputBody).toMatch(/readonly\s+token\?:\s*TraceTokenUsage\s*\|\s*null/)
    expect(inputBody).toMatch(/readonly\s+costUsd\?:\s*number\s*\|\s*null/)
  })

  it("createTraceEvent passes token + costUsd through; formatOtelStdoutLine emits OTLP attributes", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    // createTraceEvent body carries token + costUsd.
    const ctorMatch = src.match(
      /export function createTraceEvent\([^)]*\):\s*TraceEvent\s*\{([\s\S]*?)\n\}/,
    )
    expect(ctorMatch, "createTraceEvent body not found").not.toBeNull()
    const ctorBody = ctorMatch?.[1] ?? ""
    expect(ctorBody).toMatch(/token:\s*input\.token\s*\?\?\s*null/)
    expect(ctorBody).toMatch(/costUsd:\s*input\.costUsd\s*\?\?\s*null/)
    // OTLP attribute emission.
    expect(src).toMatch(/butler\.token\.inputTokens/)
    expect(src).toMatch(/butler\.token\.outputTokens/)
    expect(src).toMatch(/butler\.token\.totalTokens/)
    expect(src).toMatch(/butler\.costUsd/)
  })
})