/**
 * Arch guard (D44 P5 Model Port): lock the Model Port seam.
 *
 * P5 Materialization:
 *   - `packages/ports/src/core/model-port.ts` is the single source of
 *     truth for role-level provider + model selection (DESIGN §6.2
 *     "协议适配 + 用量记账").
 *   - adapters build LLMAdapters from that resolution (D31 §7 依赖方向
 *     向内 — adapters attribute into ports, never the reverse).
 *   - apps-api pricing resolves the active model from the same Port so
 *     accounting matches real routing (D24 costUsd unified).
 *
 * Static checks (no runtime):
 *   - model-port.ts exists at `packages/ports/src/core/model-port.ts`
 *     and exports `resolveModelForRole` / `ModelRole` / `ResolvedModel`.
 *   - model-port.ts is pure: 0 `LLMAdapter` import, 0 fetch / db / IO
 *     (satisfies D31 §7 interface-only + dependency-inward).
 *   - `packages/adapters/src/model-router.ts` imports
 *     `@butler/ports/core/model-port.js` (adapter depends on the Port).
 *   - `apps/api/src/llm-pricing.ts` imports `@butler/ports/core/model-port.js`
 *     and still exports `resolveCurrentLlmModel` (§14 plumbing chain intact).
 *
 * Runtime behavior is verified by:
 *   - `packages/ports/src/core/model-port.test.ts`
 *   - `packages/adapters/src/model-router.test.ts`
 *   - `apps/api/src/llm-pricing.test.ts`
 */
import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const MODEL_PORT = join(__dirname, "../../packages/ports/src/core/model-port.ts")
const MODEL_ROUTER = join(__dirname, "../../packages/adapters/src/model-router.ts")
const LLM_PRICING = join(__dirname, "../../apps/api/src/llm-pricing.ts")

describe("arch: P5 Model Port (D44 — role-level provider/model single source of truth)", () => {
  it("ports/core/model-port.ts exists and exports resolveModelForRole / ModelRole / ResolvedModel, and is pure (0 LLMAdapter / 0 fetch/db)", () => {
    const src = readFileSync(MODEL_PORT, "utf-8")
    expect(src).toMatch(/export\s+function\s+resolveModelForRole\s*\(/)
    expect(src).toMatch(/export\s+type\s+ModelRole\b/)
    expect(src).toMatch(/export\s+interface\s+ResolvedModel\s*\{/)
    // Port is pure: no adapters protocol-surface import, no IO.
    expect(src).not.toMatch(/import\s*[^"']*LLMAdapter/)
    expect(src).not.toMatch(/from\s+["'][^"']*(llm-provider|@butler\/adapters)/)
    expect(src).not.toMatch(/\bfetch\s*\(|pgTable\s*\(|new\s+(Pool|Client)\b/)
  })

  it("adapters model-router imports @butler/ports/core/model-port.js (依赖方向向内)", () => {
    const src = readFileSync(MODEL_ROUTER, "utf-8")
    expect(src).toMatch(/from\s+["']@butler\/ports\/core\/model-port\.js["']/)
  })

  it("apps llm-pricing imports the Model Port for accounting and keeps resolveCurrentLlmModel (§14 chain)", () => {
    const src = readFileSync(LLM_PRICING, "utf-8")
    expect(src).toMatch(/from\s+["']@butler\/ports\/core\/model-port\.js["']/)
    expect(src).toMatch(/resolveModelForRole\(env,\s*["']plan["']\)/)
    expect(src).toMatch(/export\s+function\s+resolveCurrentLlmModel\s*\(/)
  })
})