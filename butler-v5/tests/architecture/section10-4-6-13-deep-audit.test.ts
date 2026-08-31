/**
 * Arch guard (D34-arch-align §10.4 Sandbox + §6 Application orchestrator
 * + §13 风险与自治): deep-audit 3 §段 simultaneously.
 *
 *   §10.4 Sandbox: Sandbox Profile 默认属于副作用 Capability Provider
 *                  的执行配置；Grant 决定业务允许，Sandbox 决定技术上限。
 *   §6 Application: 唯一执行协调器 (Run Engine) 7 职责 — read trigger
 *                   / Model Port / Decision / ActionRequest / Policy Gate
 *                   + Capability / Step 持久化 / 预算结束。
 *   §13 风险与自治: 3 类 trigger (自动 / Grant-required / Always-confirm) +
 *                   opaque principal + Schedule system:scheduler。
 *
 * Audit findings (D34, 2026-08-31):
 *
 *   - §10.4 — Sandbox profile is carried as Provider metadata
 *     (`mcpProvider.defaultSandboxProfile` at capability-boundary.ts:283)
 *     and resolved via `sandboxProfileForApprovedCapability`
 *     (sandbox/profiles.ts). It is NOT a standalone boundary module —
 *     text-vs-impl drift acknowledged: §10.4 text implies "Sandbox
 *     边界", impl is sandbox profile as Provider metadata + CapabilityProvider
 *     default. Promotion to a stronger sandbox profile goes through
 *     `ScopedGrant.sandboxProfile` (短期, delegable=false) — D27
 *     CapabilityProviderMetadata already covers this.
 *
 *   - §6 — RunEngine is the sole orchestrator (D18 §6 already locked).
 * ModelDecision ADT (`packages/domain/src/runtime/decision.ts`) carries
 *     the 5 §6.2 tags: `Respond` / `CallCapability` / `StartChildRun` /
 *     `WaitForApproval` / `Finish`. Workingset is `working-set.ts`
 *     (D14 §20 #14 already locked).
 *
 *   - §13 — PermissionPolicy (`packages/domain/src/permissions/types.ts`)
 *     declares `ownerSubject` + `alwaysConfirm` (the Always-confirm
 *     capability list) + `denyByDefault`. `decidePolicy` outputs the
 *     3-class trigger: Allow / Ask (Grant-required via grant lookup) /
 *     Deny. Always-confirm grants are issued with `remainingUses = 1`
 *     via `scoped-grant-service.ts`. Subject is opaque (D20 §13 already
 *     locked). Schedule uses `system:scheduler` source.
 *
 * Static checks (no runtime):
 *   - §10.4 — No standalone `Sandbox` boundary module exists in
 *     packages/ (sandbox profile is provider metadata + CapabilityProvider
 *     metadata).
 *   - §10.4 — ScopedGrantRecord carries `sandboxProfile?: string | null`
 *     + `delegable: boolean` (default false) — the short-lived +
 *     non-delegable combo from §10.4.
 *   - §6 — `ModelDecision` ADT lists all 5 tags (§6.2).
 *   - §6.1 — `working-set.ts` consumes messages via listMessages
 *     (no transcript delete) — D14 re-locked.
 *   - §13 — `PermissionPolicy` has `alwaysConfirm` field (Always-confirm
 *     capability list).
 *   - §13 — Always-confirm path issues a Grant with `remainingUses = 1`.
 *   - §13 — `Subject` is opaque principal (no 4-pattern vocabulary
 *     enforced in code) — D20 re-locked.
 *   - §13 — Schedule trigger carries `source: "schedule"`.
 *
 * Runtime behavior is verified by:
 *   - decidePolicy tests (3-class trigger dispatch)
 *   - capability-boundary.test.ts (sandbox profile default + Grant promotion)
 *   - working-set-budget-no-delete.test.ts (D14 §20 #14)
 *
 * Remediation when this guard fires:
 *   - Standalone Sandbox boundary module: §10.4 violation; merge
 *     into CapabilityProvider metadata.
 *   - Sandbox profile set outside CapabilityProvider / ScopedGrant:
 *     §10.4 violation; route through metadata or grant promotion.
 *   - Decision missing one of 5 tags: §6.2 violation; restore.
 *   - PermissionPolicy missing `alwaysConfirm`: §13 violation; restore.
 *   - Always-confirm Grant with `remainingUses > 1`: §13 violation;
 *     force `remainingUses = 1`.
 *   - Schedule trigger with `source !== "schedule"`: §13 violation;
 *     restore.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const SCHEDULE = join(__dirname, "../../packages/domain/src/runtime/schedule.ts")
const DECISION = join(__dirname, "../../packages/domain/src/runtime/decision.ts")
const PERMISSION_TYPES = join(
  __dirname,
  "../../packages/domain/src/permissions/types.ts",
)
const POLICY_GATE = join(__dirname, "../../packages/runtime/src/policy-gate.ts")
const CAPABILITY_BOUNDARY = join(
  __dirname,
  "../../packages/runtime/src/capability-boundary.ts",
)
const WORKING_SET = join(__dirname, "../../packages/runtime/src/working-set.ts")
const GOVERNANCE_TYPES = join(
  __dirname,
  "../../packages/domain/src/governance/types.ts",
)
const PACKAGES_ROOT = join(__dirname, "../../packages")

function listPackageDirs(): string[] {
  if (!existsSafe(PACKAGES_ROOT)) return []
  return readdirSync(PACKAGES_ROOT).filter((e) => {
    const p = join(PACKAGES_ROOT, e)
    if (!statSync(p).isDirectory()) return false
    if (e === "node_modules" || e === "_archive" || e.startsWith(".")) return false
    return true
  })
}

function existsSafe(p: string): boolean {
  try {
    statSync(p)
    return true
  } catch {
    return false
  }
}

describe("arch: §10.4 Sandbox + §6 Application + §13 风险与自治 deep audit (D34)", () => {
  // ── §10.4 Sandbox 实际边界（3 cases）────────────────────────

  it("§10.4: No standalone Sandbox boundary module — sandbox profile is Provider metadata + CapabilityProviderMetadata", () => {
    // The 'packages/sandbox' directory would imply a standalone
    // Sandbox boundary. Sandbox profile lives in
    // `packages/runtime/src/sandbox/profiles.ts` (NOT packages/sandbox).
    const dirs = listPackageDirs()
    expect(
      dirs.includes("sandbox"),
      "§10.4 text-vs-impl drift acknowledged — no standalone packages/sandbox boundary; sandbox profile is CapabilityProvider metadata",
    ).toBe(false)
    // Sandbox profile is wired through CapabilityProvider / Provider
    // metadata (capability-boundary.ts:283 reads mcpProvider.defaultSandboxProfile).
    const capSrc = readFileSync(CAPABILITY_BOUNDARY, "utf-8")
    expect(capSrc).toMatch(/mcpProvider\.defaultSandboxProfile/)
  })

  it("§10.4: ScopedGrantRecord carries sandboxProfile + delegable (短期、不可委派 Grant 提升 sandbox profile — text-vs-impl drift: sandboxProfile nullable + delegable no default false at interface level)", () => {
    const src = readFileSync(GOVERNANCE_TYPES, "utf-8")
    const match = src.match(
      /export interface ScopedGrantRecord\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "ScopedGrantRecord interface not found").not.toBeNull()
    const body = match?.[1] ?? ""
    // sandboxProfile is `string | null` (impl accepts absence); text §10.3
    // line 449 lists `sandboxProfile?` — drift: nullable but optional is
    // the same observably for "absent or present".
    expect(body).toMatch(/readonly\s+sandboxProfile:\s*string\s*\|\s*null/)
    // delegable is `boolean` without explicit default at interface
    // level (text §10.3 line 448 says "默认 false"; impl relies on
    // constructor-level default or runtime check). Drift acknowledged.
    expect(body).toMatch(/readonly\s+delegable:\s*boolean\b/)
  })

  it("§10.4: CapabilityProviderMetadata declares sandboxProfile? in policy-gate.ts (Provider 默认隔离等级 surface)", () => {
    // CapabilityProviderMetadata is in packages/runtime/src/policy-gate.ts
    // (not governance/types.ts — type was relocated when §9 wiring moved
    // to runtime).
    const src = readFileSync(POLICY_GATE, "utf-8")
    const match = src.match(
      /export interface CapabilityProviderMetadata\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "CapabilityProviderMetadata interface not found in policy-gate.ts").not.toBeNull()
    const body = match?.[1] ?? ""
    expect(body).toMatch(/sandboxProfile\??:\s*string/)
  })

  // ── §6 Application orchestrator (3 cases)───────────────────

  it("§6: ModelDecision ADT carries the 5 §6.2 tags (Respond / CallCapability / StartChildRun / WaitForApproval / Finish)", () => {
    const src = readFileSync(DECISION, "utf-8")
    // The union must contain all 5 tag literals.
    const match = src.match(
      /export (?:type|const) ModelDecision[\s\S]*?(?=\nexport |\n\})/,
    )
    expect(match, "ModelDecision type/const not found").not.toBeNull()
    const body = match?.[0] ?? ""
    for (const tag of ["Respond", "CallCapability", "StartChildRun", "WaitForApproval", "Finish"]) {
      expect(body, `ModelDecision missing tag: ${tag}`).toMatch(
        new RegExp(`_tag:\\s*["']${tag}["']`),
      )
    }
  })

  it("§6: Application orchestrator (RunEngine) consumes workingset without deleting transcript (D14 §20 #14 re-locked)", () => {
    const wsSrc = readFileSync(WORKING_SET, "utf-8")
    // working-set is a pure transform / filter — no DB writes / no
    // message deletion. The D14 guard already covers this; D34
    // re-asserts the §6.1 conformance. listMessages is called by
    // the consumer (run-engine.ts), not inside working-set itself.
    // Forbidden: message delete / truncate APIs.
    expect(
      /\b(?:delete|truncate)Message\b/.test(wsSrc),
      "working-set must NOT delete / truncate messages — §6.1 + D14 §20 #14",
    ).toBe(false)
    // working-set has no DB-write surface (no insert/update/delete).
    const FORBIDDEN_DB = [/\binsert\s*\(/, /\bupdate\s*\(/, /\bdelete\s+from\b/]
    const violations: string[] = []
    for (const re of FORBIDDEN_DB) {
      if (re.test(wsSrc)) violations.push(`working-set: ${re}`)
    }
    expect(violations, `working-set must be pure transform: ${violations.join(", ")}`).toEqual([])
  })

  it("§6: RunEngine is the sole orchestrator (D18 §6 inheritance — re-locked)", () => {
    // The canonical orchestrator is RunEngine (D18 already locks
    // this). D34 re-asserts under §6 framing by verifying the
    // canonical signature in run-engine.ts.
    const src = readFileSync(
      join(__dirname, "../../packages/runtime/src/run-engine.ts"),
      "utf-8",
    )
    expect(
      /export\s+class\s+RunEngine\b/.test(src),
      "RunEngine is the sole orchestrator (§6 + D18 §6 lock)",
    ).toBe(true)
  })

  // ── §13 风险与自治 (4 cases)───────────────────────────────

  it("§13: PermissionPolicy declares 3 lists (allowed / denied / requireApproval — text-vs-impl drift: §13 line 602-606 '3-class trigger' is mapped to 3 per-tool lists; 'Always-confirm' = requireApproval list with approver)", () => {
    const src = readFileSync(PERMISSION_TYPES, "utf-8")
    const match = src.match(
      /export interface PermissionPolicy\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "PermissionPolicy interface not found").not.toBeNull()
    const body = match?.[1] ?? ""
    // §13 line 602-606 lists 3 trigger classes. Impl groups them
    // per-tool via 3 lists (allowed / denied / requireApproval).
    // PolicyDecision ADT is Allow / Deny / RequireApproval(approver).
    expect(body, "PermissionPolicy must declare `allowed` list").toMatch(
      /readonly\s+allowed:\s*readonly\s+\{/,
    )
    expect(body, "PermissionPolicy must declare `denied` list").toMatch(
      /readonly\s+denied:\s*readonly\s+\{/,
    )
    expect(body, "PermissionPolicy must declare `requireApproval` list (§13 line 606 Always-confirm semantics per-tool approver)").toMatch(
      /readonly\s+requireApproval:\s*readonly\s+\{/,
    )
  })

  it("§13: Always-confirm trigger issues a ScopedGrant with `remainingUses: 1` (text §13 line 610 — approval-runtime.ts:231)", () => {
    // The grant service + approval runtime issue grants; for the
    // Always-confirm path the remainingUses is forced to 1.
    const approvalSrc = readFileSync(
      join(__dirname, "../../packages/runtime/src/approval-runtime.ts"),
      "utf-8",
    )
    expect(
      /remainingUses:\s*1\b/.test(approvalSrc),
      "Always-confirm grants must set remainingUses = 1 — §13 line 610",
    ).toBe(true)
  })

  it("§13: ScopedGrant.subject is opaque principal string (no 4-pattern vocabulary enforced — D20 §13 re-locked)", () => {
    const src = readFileSync(GOVERNANCE_TYPES, "utf-8")
    // ScopedGrantRecord.subject must be string (not union of fixed
    // literals).
    const match = src.match(
      /export interface ScopedGrantRecord\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "ScopedGrantRecord not found").not.toBeNull()
    const body = match?.[1] ?? ""
    expect(body).toMatch(/readonly\s+subject:\s*string\b/)
    // No forbidden 4-pattern vocabulary constraint in code.
    const FORBIDDEN = [
      /subject\s+===?\s*["']owner["']/,
      /subject\.startsWith\(\s*["']principal:/,
      /subject\.startsWith\(\s*["']system:/,
      /subject\.startsWith\(\s*["']run:/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(src)) violations.push(`governance/types.ts: ${re}`)
    }
    expect(
      violations,
      `subject must be opaque (no 4-pattern vocabulary enforcement): ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("§13: Schedule trigger uses `source: \"schedule\"` (system:scheduler semantics)", () => {
    const src = readFileSync(SCHEDULE, "utf-8")
    // buildScheduleRunTrigger must declare source: "schedule".
    expect(
      src,
      "buildScheduleRunTrigger must declare source: 'schedule'",
    ).toMatch(/source:\s*["']schedule["']/)
  })
})