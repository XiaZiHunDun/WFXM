/**
 * Arch guard (D24-arch-align §14 costUsd pricing batch): closes the
 * D23 "costUsd reserved for future pricing batch" gap by plumbing
 * pricing from env into the step/llm_call trace event.
 *
 * Plumbing chain:
 *   1. `apps/api/src/llm-pricing.ts` declares:
 *      - `parseLlmPricing(env)` reading
 *        `BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK` /
 *        `_OUTPUT_PER_MTOK` env vars.
 *      - `computeCostUsd(usage, model, pricing)` returning USD cost
 *        or null when pricing is missing (D24: missing = null, not 0).
 *      - `resolveCurrentLlmModel(env)` returning the active model
 *        name (mirrors `pickLLMProvider`).
 *   2. The 3 ports.complete callers (`wechat-inbound-butler.ts`,
 *      `subagent-worker.ts`, `approval-resume.ts`) call all 3 helpers
 *      and pass `costUsd` into `tracer.record({ kind: "step",
 *      name: "llm_call", ..., costUsd })`.
 *   3. `TraceEvent.costUsd` (first-class, declared in D23) carries
 *      the value into OTLP via `butler.costUsd` attribute.
 *
 * Static checks (no runtime):
 *   - `llm-pricing.ts` exposes the 3 helpers + `ModelPricing` type.
 *   - Each of the 3 caller files imports + invokes all 3 helpers and
 *     passes `costUsd` into the success-branch tracer.record input.
 *   - `local-trace.ts` still declares `costUsd: number | null`
 *     first-class (D23 invariant — D24 must not regress).
 *
 * Runtime behavior is verified by:
 *   - `apps/api/src/llm-pricing.test.ts` (D24 unit tests — parse
 *     env vars, compute cost, resolve model).
 *   - `tests/architecture/section14-observability-fields.test.ts`
 *     (D21 + D23) — declares `costUsd` as a required top-level field
 *     on `TraceEvent` + `CreateTraceEventInput`.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const LLM_PRICING = join(__dirname, "../../apps/api/src/llm-pricing.ts")
const LOCAL_TRACE = join(
  __dirname,
  "../../packages/domain/src/observability/local-trace.ts",
)
const WECHAT_INBOUND_BUTLER = join(__dirname, "../../apps/api/src/wechat-inbound-butler.ts")
const SUBAGENT_WORKER = join(__dirname, "../../apps/api/src/subagent-worker.ts")
const APPROVAL_RESUME = join(__dirname, "../../apps/api/src/approval-resume.ts")

describe("arch: §14 costUsd pricing batch (D24 — D23 reserved field activated)", () => {
  // ── 1. llm-pricing module exposes the 3 helpers ───────────────

  it("llm-pricing.ts exposes parseLlmPricing + computeCostUsd + resolveCurrentLlmModel + ModelPricing", () => {
    const src = readFileSync(LLM_PRICING, "utf-8")
    expect(src).toMatch(/export\s+interface\s+ModelPricing\s*\{/)
    expect(src).toMatch(/export\s+function\s+parseLlmPricing\s*\(/)
    expect(src).toMatch(/export\s+function\s+computeCostUsd\s*\(/)
    expect(src).toMatch(/export\s+function\s+resolveCurrentLlmModel\s*\(/)
  })

  it("parseLlmPricing reads BUTLER_V5_PRICING_<MODEL>_INPUT/OUTPUT_PER_MTOK env vars", () => {
    const src = readFileSync(LLM_PRICING, "utf-8")
    expect(src).toMatch(/BUTLER_V5_PRICING_/)
    expect(src).toMatch(/_INPUT_PER_MTOK/)
    expect(src).toMatch(/_OUTPUT_PER_MTOK/)
  })

  it("computeCostUsd returns null when model pricing is missing (D24 decision)", () => {
    const src = readFileSync(LLM_PRICING, "utf-8")
    // The function body must contain a `return null` branch.
    expect(src).toMatch(/return\s+null/)
  })

  // ── 2. caller imports + invokes the 3 helpers + passes costUsd ─

  it("wechat-inbound-butler imports all 3 pricing helpers and passes costUsd into step/llm_call trace", () => {
    const src = readFileSync(WECHAT_INBOUND_BUTLER, "utf-8")
    expect(src).toMatch(/import\s*\{[^}]*parseLlmPricing[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*computeCostUsd[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*resolveCurrentLlmModel[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    // Helpers are invoked before the LLM call completes.
    expect(src).toMatch(/parseLlmPricing\(env\)/)
    expect(src).toMatch(/resolveCurrentLlmModel\(env\)/)
    // costUsd is computed from usage + model + pricing, then passed
    // into the step/llm_call tracer.record input.
    expect(src).toMatch(/computeCostUsd\(resp\.usage,\s*currentModel,\s*pricing\)/)
    expect(src).toMatch(/costUsd,?\s*\n\s*\}\)/)
  })

  it("subagent-worker imports all 3 pricing helpers and passes costUsd into step/llm_call trace", () => {
    const src = readFileSync(SUBAGENT_WORKER, "utf-8")
    expect(src).toMatch(/import\s*\{[^}]*parseLlmPricing[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*computeCostUsd[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*resolveCurrentLlmModel[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/parseLlmPricing\(env\)/)
    expect(src).toMatch(/resolveCurrentLlmModel\(env\)/)
    expect(src).toMatch(/computeCostUsd\(resp\.usage,\s*currentModel,\s*pricing\)/)
    expect(src).toMatch(/costUsd,?\s*\n\s*\}\)/)
  })

  it("approval-resume imports all 3 pricing helpers and passes costUsd into step/llm_call trace", () => {
    const src = readFileSync(APPROVAL_RESUME, "utf-8")
    expect(src).toMatch(/import\s*\{[^}]*parseLlmPricing[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*computeCostUsd[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    expect(src).toMatch(/import\s*\{[^}]*resolveCurrentLlmModel[^}]*\}\s*from\s*["']\.\/llm-pricing\.js["']/)
    // approval-resume passes `args.env` (not bare `env`) to the helpers.
    expect(src).toMatch(/parseLlmPricing\(args\.env\)/)
    expect(src).toMatch(/resolveCurrentLlmModel\(args\.env\)/)
    expect(src).toMatch(/computeCostUsd\(resp\.usage,\s*currentModel,\s*pricing\)/)
    expect(src).toMatch(/costUsd,?\s*\n\s*\}\)/)
  })

  // ── 3. TraceEvent.costUsd first-class invariant ──────────────

  it("TraceEvent still declares costUsd: number | null first-class (D23 invariant)", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    const traceEventMatch = src.match(
      /export interface TraceEvent\s*\{([\s\S]*?)\n\}/,
    )
    expect(traceEventMatch, "TraceEvent interface not found").not.toBeNull()
    const body = traceEventMatch?.[1] ?? ""
    expect(body).toMatch(/readonly\s+costUsd:\s*number\s*\|\s*null/)
    const inputMatch = src.match(
      /export interface CreateTraceEventInput\s*\{([\s\S]*?)\n\}/,
    )
    expect(inputMatch, "CreateTraceEventInput interface not found").not.toBeNull()
    const inputBody = inputMatch?.[1] ?? ""
    expect(inputBody).toMatch(/readonly\s+costUsd\?:\s*number\s*\|\s*null/)
    // OTLP emission must remain (D23 invariant).
    expect(src).toMatch(/butler\.costUsd/)
  })
})