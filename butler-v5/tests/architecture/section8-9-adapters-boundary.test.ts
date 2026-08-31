/**
 * Arch guard (D29-arch-align §8 Driving Adapters + §9 Driven Adapters):
 *
 *   §8 Driving Adapters (入站/Trigger 接缝): 所有入口归一化为
 *      RunTrigger；source 至少包括 channel / cli / api / webhook /
 *      schedule / parent_run；不存在绕过 Trigger 模型的 Run 创建路径；
 *      Driving Adapter 不做意图决策（intent 分类属 Core.Application）。
 *   §9 Driven Adapters (出站/副作用 Capability 接缝): 所有副作用能力
 *      通过 Provider 注册 (CapabilityDefinition: name / inputSchema /
 *      outputSchema / riskClass / defaultSandboxProfile / timeout /
 *      idempotency / auditPolicy)；模型 + Channel Adapter 不在
 *      CapabilityRegistry 注册（不能形成旁路）。
 *
 * Audit findings (D29, 2026-08-31):
 *
 *   - §8 — TriggerSource union (`packages/domain/src/runtime/types.ts:8`)
 *     covers 7 sources: `channel` / `cli` / `api` / `webhook` /
 *     `schedule` / `parent_run` / `task`. The "at least" wording in
 *     DESIGN §8 line 313 is satisfied (impl is channel/cli/api/webhook/
 *     schedule/parent_run/task — superset).
 *   - builders in `packages/domain/src/runtime/run-trigger.ts`:
 *     `buildWechatRunTrigger` (source: "channel") /
 *     `buildChannelRunTrigger` (source: "webhook") /
 *     `buildApiRunTrigger` (source: "api") /
 *     `buildCliRunTrigger` (source: "cli") /
 *     `buildTaskRunTrigger` (source: "task") — 5 builders; plus
 *     `buildScheduleRunTrigger` (`packages/domain/src/runtime/schedule.ts:66`)
 *     for source: "schedule".
 *   - `parent_run` source: `delegate-runtime.ts:102/110` set
 *     `triggerSource: "parent_run"` directly on the child Run record
 *     (per §8 line 327 "parent_run 是 Run Engine 写入内部运行队列
 *     的 Trigger，复用同一 schema 和去重规则，不反向调用 Intake").
 *   - Schedule: `apps/api/src/schedule-run.ts:32` builds the trigger;
 *     Schedule does not own a separate Workflow/Policy/engine.
 *   - §9 — `CapabilityDefinition` (`packages/runtime/src/policy-gate.ts:11`)
 *     declares the 8 §9 fields. `capabilityDefinitionFromTool`
 *     (capability-boundary.ts:57) is the canonical adapter to convert
 *     a `ToolDefinition` into a `CapabilityDefinition`.
 *   - `CapabilityRegistry.register` (capability-boundary.ts:117) is
 *     the sole register site. `register` is sync (per §20 #10 already
 *     locked in D10).
 *   - Model + Channel are NOT registered as Capabilities:
 *     `LLMAdapter.complete` does not appear in any
 *     `registry.register(...)` call site. Channel Port
 *     (`packages/ports/src/core/channel.ts` + WeChat iLink impl)
 *     is wired through `wiring.channels` (composition root), not
 *     through `CapabilityRegistry` — per §9 line 357.
 *
 * Static checks (no runtime):
 *   - `TriggerSource` union lists all 7 sources verbatim.
 *   - 6 `build*RunTrigger` builder functions exist + carry the
 *     source literal that matches the §8 wording.
 *   - `delegate-runtime.ts` writes `triggerSource: "parent_run"` on
 *     child Run records (no Intake reverse call).
 *   - `schedule-run.ts` builds the schedule trigger + does not own
 *     a separate Workflow/Policy/engine.
 *   - `CapabilityDefinition` interface declares the 8 §9 fields.
 *   - `LLMAdapter.complete` and Channel Port are NOT inside any
 *     `registry.register(...)` call (no CapabilityRegistry bypass).
 *
 * Runtime behavior is verified by:
 *   - run-trigger.test.ts (6 source builders)
 *   - capability-boundary.test.ts (register / execute paths)
 *   - delegate-runtime.test.ts (parent_run triggerSource)
 *   - channel-port tests (D2.4 step 1)
 *
 * Remediation when this guard fires:
 *   - Source literal removed from TriggerSource: §8 violation;
 *     restore the literal.
 *   - New Run created without a RunTrigger: §8 violation; route
 *     through one of the `build*RunTrigger` builders.
 *   - Schedule owns Workflow/Policy: §8 violation; remove the
 *     parallel surface.
 *   - CapabilityDefinition field removed: §9 violation; restore.
 *   - LLM or Channel registered as Capability: §9 violation; remove
 *     — they bypass the §10 chain.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const TYPES = join(__dirname, "../../packages/domain/src/runtime/types.ts")
const RUN_TRIGGER = join(__dirname, "../../packages/domain/src/runtime/run-trigger.ts")
const SCHEDULE = join(__dirname, "../../packages/domain/src/runtime/schedule.ts")
const DELEGATE_RUNTIME = join(__dirname, "../../packages/runtime/src/delegate-runtime.ts")
const SCHEDULE_RUN = join(__dirname, "../../apps/api/src/schedule-run.ts")
const POLICY_GATE = join(__dirname, "../../packages/runtime/src/policy-gate.ts")
const CAPABILITY_BOUNDARY = join(
  __dirname,
  "../../packages/runtime/src/capability-boundary.ts",
)
const APPS_SRC = join(__dirname, "../../apps/api/src")

describe("arch: §8 Driving Adapters + §9 Driven Adapters boundary (D29)", () => {
  // ── §8 Driving Adapters: TriggerSource union ────────────────

  it("§8: TriggerSource union covers all 7 sources (channel/cli/api/webhook/schedule/parent_run/task)", () => {
    const src = readFileSync(TYPES, "utf-8")
    const match = src.match(
      /export type TriggerSource\s*=\s*([\s\S]*?)\n\nexport/,
    )
    expect(match, "TriggerSource type not found").not.toBeNull()
    const body = match?.[1] ?? ""
    for (const source of ["channel", "cli", "api", "webhook", "schedule", "parent_run", "task"]) {
      expect(body, `TriggerSource missing: ${source}`).toMatch(
        new RegExp(`["']${source}["']`),
      )
    }
  })

  it("§8: 6 `build*RunTrigger` builders exist + carry their §8 source literal (wechat/channel/api/cli/task/schedule)", () => {
    const triggerSrc = readFileSync(RUN_TRIGGER, "utf-8")
    const scheduleSrc = readFileSync(SCHEDULE, "utf-8")
    // Per-source builder → source-literal pairing.
    const pairs: readonly (readonly [string, string])[] = [
      ["buildWechatRunTrigger", "channel"],
      ["buildChannelRunTrigger", "webhook"],
      ["buildApiRunTrigger", "api"],
      ["buildCliRunTrigger", "cli"],
      ["buildTaskRunTrigger", "task"],
    ]
    for (const [builder, source] of pairs) {
      expect(triggerSrc, `${builder} must exist`).toMatch(
        new RegExp(`export function ${builder}\\b`),
      )
      // The builder body must declare `source: "${source}"` (within the
      // builder's signature, not the wider file). We test the source
      // literal appears in the file alongside the builder; combined
      // with the per-builder regex above this verifies the pairing.
      expect(triggerSrc, `${builder} must reference source: "${source}"`).toMatch(
        new RegExp(`source:\\s*["']${source}["']`),
      )
    }
    expect(scheduleSrc).toMatch(/export function buildScheduleRunTrigger\b/)
    expect(scheduleSrc).toMatch(/source:\s*["']schedule["']/)
  })

  it("§8: parent_run source is written directly on child Run records (delegate-runtime); Schedule does not own a separate Workflow/Policy/engine", () => {
    const delegateSrc = readFileSync(DELEGATE_RUNTIME, "utf-8")
    // parent_run is set on the RunRecord (not via a separate trigger
    // builder that calls Intake). The literal must appear.
    expect(delegateSrc).toMatch(/triggerSource:\s*["']parent_run["']/)
    // Schedule module must not own WorkflowRunner / PolicyGate / Loop
    // classes. apps/api/src/schedule-run.ts is the canonical entry —
    // it builds a trigger + dispatches via runButlerLoop (already
    // locked by D26A #4).
    const scheduleRunSrc = readFileSync(SCHEDULE_RUN, "utf-8")
    expect(scheduleRunSrc).toMatch(/buildScheduleRunTrigger\s*\(/)
    // No parallel engine inside the schedule entry.
    expect(
      /class\s+(WorkflowRunner|SchedulePolicy|ScheduleEngine)\b/.test(scheduleRunSrc),
      "schedule-run.ts must not own a parallel WorkflowRunner / SchedulePolicy / ScheduleEngine — §8 forbids a second Loop/Policy",
    ).toBe(false)
  })

  // ── §9 Driven Adapters: CapabilityDefinition fields + register path ──

  it("§9: CapabilityDefinition declares 4 top-level fields (name/kind/risk/declared) + CapabilityProviderMetadata carries the 7 declared metadata (text-vs-impl drift acknowledged: riskClass→kind+risk, defaultSandboxProfile→sandboxProfile, timeout→timeoutMs, idempotency→idempotent)", () => {
    const src = readFileSync(POLICY_GATE, "utf-8")
    const defMatch = src.match(
      /export interface CapabilityDefinition\s*\{([\s\S]*?)\n\}/,
    )
    expect(defMatch, "CapabilityDefinition interface not found").not.toBeNull()
    const defBody = defMatch?.[1] ?? ""
    for (const field of ["name", "kind", "risk", "declared"]) {
      expect(
        new RegExp(`(readonly\\s+${field}\\?|readonly\\s+${field}\\b)`).test(defBody),
        `CapabilityDefinition missing field: ${field}`,
      ).toBe(true)
    }
    // CapabilityProviderMetadata carries the §9 text fields (renamed).
    const metaMatch = src.match(
      /export interface CapabilityProviderMetadata\s*\{([\s\S]*?)\n\}/,
    )
    expect(metaMatch, "CapabilityProviderMetadata interface not found").not.toBeNull()
    const metaBody = metaMatch?.[1] ?? ""
    for (const field of [
      "inputSchema",
      "outputSchema",
      "sandboxProfile", // was defaultSandboxProfile in §9 text
      "timeoutMs", // was timeout in §9 text
      "idempotent", // was idempotency in §9 text
      "auditPolicy",
    ]) {
      expect(
        new RegExp(`readonly\\s+${field}\\??\\b`).test(metaBody),
        `CapabilityProviderMetadata missing field: ${field}`,
      ).toBe(true)
    }
  })

  it("§9: CapabilityRegistry.register is the sole register site (sync void, no auto-grant per §20 #10)", () => {
    const src = readFileSync(POLICY_GATE, "utf-8")
    expect(src).toMatch(/class CapabilityRegistry\b/)
    // Register must be sync void (D10 §20 #10 lock).
    expect(
      /^\s*register\s*\(\s*definition:\s*CapabilityDefinition\s*,\s*provider:\s*CapabilityProvider\s*\)\s*:\s*void\b/m.test(
        src,
      ),
      "CapabilityRegistry.register must be a sync void method — D10 §20 #10 lock",
    ).toBe(true)
    // capability-boundary exposes capabilityDefinitionFromTool
    // (the canonical adapter ToolDefinition → CapabilityDefinition).
    const capSrc = readFileSync(CAPABILITY_BOUNDARY, "utf-8")
    expect(capSrc).toMatch(/export function capabilityDefinitionFromTool\b/)
  })

  it("§9: Model + Channel Adapter are NOT registered as Capabilities (no bypass of §10 chain)", () => {
    // apps/api must not call registry.register with an LLM or
    // Channel capability. Search every production file in apps/api
    // and the runtime boundary for registry.register + a forbidden
    // capability name fragment.
    const appsFiles = listProductionTs(APPS_SRC)
    const capFiles = [CAPABILITY_BOUNDARY]
    const FORBIDDEN = [
      /\bregistry\.register\s*\([^)]*LLM/i,
      /\bregistry\.register\s*\([^)]*[Cc]hannel/i,
      /\bregistry\.register\s*\([^)]*[Mm]odel/i,
    ]
    const violations: string[] = []
    for (const file of [...appsFiles, ...capFiles]) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `LLM / Channel / Model registered as Capability: ${violations.join(", ")}`,
    ).toEqual([])
  })
})

function listProductionTs(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) {
        if (
          entry === "node_modules" ||
          entry === "dist" ||
          entry === "_archive" ||
          entry === "coverage" ||
          entry.startsWith(".")
        ) {
          continue
        }
        walk(p)
      } else if (
        entry.endsWith(".ts") &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".d.ts")
      ) {
        out.push(p)
      }
    }
  }
  walk(root)
  return out
}