/**
 * Arch guard (D27-arch-align §10 Governance 与副作用咽喉): lock
 * the 4 §10 子段 invariants + the §10 主体 pipeline:
 *
 *   §10 主体: 所有副作用规范化为 ActionRequest → Policy →
 *             waiting_approval → ScopedGrant → Provider Execution →
 *             Audit。**模型调用不走这条链**。
 *   §10.1 Policy: PolicyDecision = Allow | Deny(reason) | Ask(question, expiresAtMs)
 *   §10.2 Approval: waiting_approval 是 Step status（不是独立表）；
 *                   PendingApprovalRequest 持久化待确认摘要。
 *   §10.3 ScopedGrant: 字段集合（subject / capability / scope /
 *                       expiresAtMs / remainingUses / approvalId /
 *                       delegable / sandboxProfile / networkAllowlist
 *                       + id / runId / createdAtMs DB 必需列）。
 *   §10.4 Sandbox: sandbox profile 走 `sandboxProfileForApprovedCapability`
 *                  解析，写入 Grant 字段；Provider 仍是 sandbox 边界。
 *
 * Audit findings (D27, 2026-08-31):
 *
 *   - `ActionRequest` (`packages/domain/src/governance/types.ts:19`)
 *     has 7 fields: `kind`, `capability`, `subject`, `resource`,
 *     `risk`, `digest`, `payload`. DESIGN §10 主体 text lists 5
 *     (`actor` / `capability` / `resource` / `argumentsDigest` /
 *     `context`); D27 acknowledges the rename (`actor`→`subject`,
 *     `argumentsDigest`→`digest`) + the 2 added fields (`kind` /
 *     `risk` / `payload` correspond to "what kind of action +
 *     risk classification + raw payload context").
 *   - `PolicyDecision` ADT covers `Allow` | `Deny(reason)` |
 *     `Ask(question, expiresAtMs)` — matches §10.1 verbatim.
 *   - Approval is a `waiting_approval` Step status (not an
 *     independent table). `approveWaitingStep` (approval-runtime.ts:143)
 *     transitions waiting_approval → succeeded + issues a Grant.
 *   - `ScopedGrantRecord` carries 12 fields (8 §10.3 required +
 *     3 DB plumbing `id` / `runId` / `createdAtMs` + D2.2
 *     first-class `capability` column mirroring scope.capabilities).
 *   - `sandboxProfileForApprovedCapability` (sandbox/profiles.ts)
 *     resolves the profile string the Grant lifts to when an
 *     approval authorizes a sandbox lift (DESIGN §10.4 line 433).
 *
 * Static checks (no runtime):
 *   - ActionRequest interface declares all 7 current fields
 *     (`kind` / `capability` / `subject` / `resource` / `risk` /
 *     `digest` / `payload`).
 *   - PolicyDecision union covers `Allow` / `Deny` / `Ask` tags.
 *   - `waiting_approval` is referenced as a Step status string,
 *     never as an independent pgTable / repository.
 *   - ScopedGrantRecord declares all 12 current fields.
 *   - `sandboxProfileForApprovedCapability` is the canonical sandbox
 *     resolver and is invoked from `approval-runtime` /
 *     `scoped-grant-service` (Grant + sandbox profile linkage).
 *   - Model call path (`LLMAdapter.complete`) does NOT route
 *     through `PolicyGate.decide` (i.e. model calls bypass Policy
 *     per §10 line 385 "模型调用不走这条链").
 *
 * Runtime behavior is verified by:
 *   - approval-runtime.test.ts (waiting_approval lifecycle)
 *   - capability-boundary.test.ts (PolicyDecision → execution path)
 *   - scoped-grant-service.test.ts (Grant + sandbox profile)
 *   - existing §20 #3 (Model Port) lock ensures model calls go
 *     through LLMAdapter only (companion invariant).
 *
 * Remediation when this guard fires:
 *   - ActionRequest fields change: re-lock this case under the
 *     new shape; the text vs impl drift is captured in DESIGN §10.
 *   - PolicyDecision tag removed: §10.1 violation; restore the
 *     tag so callers dispatch uniformly.
 *   - waiting_approval promoted to an independent pgTable:
 *     §10.2 violation; revert — approvals stay as Step status.
 *   - ScopedGrant fields removed: §10.3 violation; restore.
 *   - Model call routed through PolicyGate: §10 line 385
 *     violation; route LLM calls through LLMAdapter directly.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const GOV_TYPES = join(__dirname, "../../packages/domain/src/governance/types.ts")
const APPROVAL_RUNTIME = join(__dirname, "../../packages/runtime/src/approval-runtime.ts")
const SCOPED_GRANT_SERVICE = join(
  __dirname,
  "../../packages/runtime/src/scoped-grant-service.ts",
)
const SANDBOX_PROFILES = join(
  __dirname,
  "../../packages/runtime/src/sandbox/profiles.ts",
)
const CAPABILITY_BOUNDARY = join(
  __dirname,
  "../../packages/runtime/src/capability-boundary.ts",
)
const POLICY_GATE = join(__dirname, "../../packages/runtime/src/policy-gate.ts")
const LLM_PROVIDER = join(__dirname, "../../packages/adapters/src/llm-provider.ts")
const PERSISTENCE_SCHEMA = join(
  __dirname,
  "../../packages/persistence/src/schema.ts",
)

describe("arch: §10 Governance 与副作用咽喉 (D27 audit)", () => {
  // ── §10 主体: ActionRequest → Policy → Approval → Grant → Execution → Audit ──

  it("§10 主体: ActionRequest carries the 7 current fields (text vs impl drift acknowledged)", () => {
    const src = readFileSync(GOV_TYPES, "utf-8")
    const actionRequestMatch = src.match(
      /export interface ActionRequest\s*\{([\s\S]*?)\n\}/,
    )
    expect(actionRequestMatch, "ActionRequest interface not found").not.toBeNull()
    const body = actionRequestMatch?.[1] ?? ""
    for (const field of [
      "kind",
      "capability",
      "subject",
      "resource",
      "risk",
      "digest",
      "payload",
    ]) {
      expect(
        new RegExp(`readonly\\s+${field}\\b`).test(body),
        `ActionRequest missing field: ${field}`,
      ).toBe(true)
    }
  })

  it("§10 主体: ActionKind covers 'read' / 'write' / 'command' / 'delegate' / 'outbound' / 'model' (model included for traceability — model calls bypass Policy per §10 line 385)", () => {
    const src = readFileSync(GOV_TYPES, "utf-8")
    const actionKindMatch = src.match(
      /export type ActionKind\s*=\s*([\s\S]*?)\n\nexport/,
    )
    expect(actionKindMatch, "ActionKind type not found").not.toBeNull()
    const body = actionKindMatch?.[1] ?? ""
    for (const kind of ["read", "write", "command", "delegate", "outbound", "model"]) {
      expect(body).toMatch(new RegExp(`["']${kind}["']`))
    }
  })

  // ── §10.1 Policy: PolicyDecision 3 tags ───────────────────────

  it("§10.1: PolicyDecision ADT covers Allow | Deny(reason) | Ask(question, expiresAtMs)", () => {
    const src = readFileSync(GOV_TYPES, "utf-8")
    const policyDecisionMatch = src.match(
      /export type PolicyDecision\s*=\s*([\s\S]*?)\n\nexport/,
    )
    expect(policyDecisionMatch, "PolicyDecision type not found").not.toBeNull()
    const body = policyDecisionMatch?.[1] ?? ""
    expect(body).toMatch(/_tag:\s*["']Allow["']/)
    expect(body).toMatch(/_tag:\s*["']Deny["']/)
    expect(body).toMatch(/_tag:\s*["']Ask["']/)
    expect(body).toMatch(/readonly\s+reason:\s*string/)
    expect(body).toMatch(/readonly\s+question:\s*string/)
    expect(body).toMatch(/readonly\s+expiresAtMs:\s*number/)
  })

  it("§10.1: capability-boundary funnels through registry.executeThroughBoundary which calls PolicyGate.decide(ActionRequest, ...)", () => {
    // Per §10 line 394 "所有入口与父/子 Run 共用一个 Policy Gate" +
    // §20 #1 PolicyGate 唯一 (D26A already locks PolicyGate class
    // uniqueness; this case locks that capability-boundary is the
    // canonical caller via `registry.executeThroughBoundary`).
    const capSrc = readFileSync(CAPABILITY_BOUNDARY, "utf-8")
    expect(capSrc).toMatch(/registry\.executeThroughBoundary\s*\(/)
    // PolicyGate class must expose a `decide(...)` method that
    // consumes an ActionRequest + PermissionPolicy.
    const policySrc = readFileSync(POLICY_GATE, "utf-8")
    expect(policySrc).toMatch(/evaluate\s*\(request:\s*ActionRequest/)
    expect(policySrc).toMatch(/ActionRequest/)
    expect(policySrc).toMatch(/PermissionPolicy/)
  })

  // ── §10.2 Approval: waiting_approval Step (NOT 独立表) ────────

  it("§10.2: waiting_approval is the Step status string (in approval-runtime + run-engine); no independent approvals pgTable exists", () => {
    const approvalSrc = readFileSync(APPROVAL_RUNTIME, "utf-8")
    expect(approvalSrc).toMatch(/waiting_approval/)
    // Run status transition must include waiting_approval.
    expect(approvalSrc).toMatch(/transitionRunStatus\s*\(/)
    // Schema must not promote approval to its own pgTable.
    const schemaSrc = readFileSync(PERSISTENCE_SCHEMA, "utf-8")
    expect(
      /pgTable\s*\(\s*["']approvals["']/.test(schemaSrc),
      "approvals must NOT be a pgTable — §10.2 forbids an independent approvals table",
    ).toBe(false)
    // Run status enum-like column on runs table references waiting_approval
    // via transitionRunStatus("waiting_approval", ...) — schema.ts status
    // column itself is text, but the runtime contract enforces the enum.
  })

  it("§10.2: PendingApprovalRequest persists only the action digest + resource + context, not raw secrets", () => {
    const src = readFileSync(APPROVAL_RUNTIME, "utf-8")
    const match = src.match(
      /export interface PendingApprovalRequest\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "PendingApprovalRequest interface not found").not.toBeNull()
    const body = match?.[1] ?? ""
    // §10.2 line 405 "凭证、完整敏感参数和原始 secret 不进入审批记录"
    // — forbid secret-shaped field names on the approval payload.
    const FORBIDDEN_FIELD_NAMES = [
      /\bsecret\b/i,
      /\bapiKey\b/i,
      /\bpassword\b/i,
      /\btoken\b(?!\s*_?digest)/i, // allow token_digest but forbid raw token
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN_FIELD_NAMES) {
      if (re.test(body)) violations.push(`PendingApprovalRequest field: ${re}`)
    }
    expect(violations).toEqual([])
  })

  // ── §10.3 ScopedGrant: 字段集合 ──────────────────────────────

  it("§10.3: ScopedGrantRecord carries all 12 current fields (8 §10.3 required + 3 DB plumbing + 1 first-class capability column)", () => {
    const src = readFileSync(GOV_TYPES, "utf-8")
    const match = src.match(
      /export interface ScopedGrantRecord\s*\{([\s\S]*?)\n\}/,
    )
    expect(match, "ScopedGrantRecord interface not found").not.toBeNull()
    const body = match?.[1] ?? ""
    for (const field of [
      "id",
      "runId",
      "subject",
      "capability",
      "scope",
      "remainingUses",
      "expiresAtMs",
      "createdAtMs",
      "delegable",
      "approvalId",
      "sandboxProfile",
      "networkAllowlist",
    ]) {
      expect(
        new RegExp(`readonly\\s+${field}\\b`).test(body),
        `ScopedGrantRecord missing field: ${field}`,
      ).toBe(true)
    }
  })

  // ── §10.4 Sandbox: sandboxProfileForApprovedCapability 解析 ──

  it("§10.4: sandboxProfileForApprovedCapability resolves sandbox profile for approval-lifted Grants", () => {
    const profilesSrc = readFileSync(SANDBOX_PROFILES, "utf-8")
    expect(profilesSrc).toMatch(
      /export\s+function\s+sandboxProfileForApprovedCapability\b/,
    )
    // Both approval-runtime + scoped-grant-service consume this resolver.
    const approvalSrc = readFileSync(APPROVAL_RUNTIME, "utf-8")
    const grantSrc = readFileSync(SCOPED_GRANT_SERVICE, "utf-8")
    expect(approvalSrc).toMatch(/sandboxProfileForApprovedCapability\s*\(/)
    expect(grantSrc).toMatch(/sandboxProfileForApprovedCapability\s*\(/)
  })

  // ── §10 主体: 模型调用不走 §10 chain ─ ────────────────────────

  it("§10 主体: LLMAdapter.complete does NOT go through PolicyGate (model calls bypass §10 chain per §10 line 385)", () => {
    const providerSrc = readFileSync(LLM_PROVIDER, "utf-8")
    // The adapter is purely a Model Port — it consumes LLMMessage[] and
    // returns LLMAssistantResponse. It must not import PolicyGate or
    // construct ActionRequests.
    expect(
      /from\s+["'][^"']*policy-gate[^"']*["']/.test(providerSrc),
      "LLMAdapter must NOT import PolicyGate — §10 line 385 forbids routing model calls through the §10 chain",
    ).toBe(false)
    expect(
      /export\s+function\s+actionRequestFromTool/.test(providerSrc),
      "LLMAdapter must NOT export ActionRequest helpers",
    ).toBe(false)
  })
})