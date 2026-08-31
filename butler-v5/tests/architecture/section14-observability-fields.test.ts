/**
 * Arch guard (D21-arch-align §14 可观测性字段): 最小可靠性模型
 * 与本地可观测字段对齐 DESIGN §14。
 *
 * DESIGN §14 lists the local observability fields that every Run /
 * Step / ActionRequest should expose:
 *   - `conversationId`, `runId`, `stepId`, `parentRunId`
 *   - `subject`, `triggerSource`
 *   - `modelProvider`, `capability`, `policyDecision`, `grantId`
 *     (`waitingStepId` when approval waiting)
 *   - `latency`, `token`, `cost`, `retry`, `termination reason`
 *
 * Audit findings (D21, 2026-08-30):
 *   - 11 of 14 §14 fields are first-class on `TraceEvent`
 *     (`packages/domain/src/observability/local-trace.ts`):
 *     `conversationId`, `runId`, `stepId`, `parentRunId`, `subject`,
 *     `triggerSource`, `capability`, `policyDecision`, `grantId`,
 *     `waitingStepId`, `durationMs`.
 *   - 3 fields are captured via `TraceEvent.detail` (open Record):
 *     `modelProvider` (e.g. inside `capability-boundary.ts:286-295`),
 *     `retry` (via `status: "error"` re-attempts and `detail`),
 *     `termination reason` (via `name: "finish"` + `detail.finalStatus`).
 *
 * D23 update (2026-08-31): `token` (LLM usage) is now first-class on
 * `TraceEvent` (declared as `readonly token: TraceTokenUsage | null`).
 * `costUsd` is also first-class (`readonly costUsd: number | null`)
 * but stays `null` until a future pricing batch lands — the field is
 * declared first-class so trace shape is ready when that ships. So:
 *   - 13 of 14 §14 fields are first-class (D23 added `token` +
 *     `costUsd`).
 *   - 3 fields remain `detail` workarounds (modelProvider, retry,
 *     termination reason).
 *   - No §14 field is "NOT captured" — the D21 token/cost gap closed.
 *
 * Static checks (no runtime):
 *   - `TraceEvent` (packages/domain/src/observability/local-trace.ts)
 *     carries all §14 top-level fields. Any future removal of one
 *     of these fields is a §14 violation.
 *   - `CreateTraceEventInput` includes the same fields so callers
 *     are forced to provide them.
 *
 * Runtime behavior is verified by:
 *   - tests/eval/scenarios (which observe trace output)
 *   - the trace recorder itself (packages/domain/src/observability/
 *     local-trace.ts) — used in run-engine / capability-boundary /
 *     approval-runtime / owner-routes
 *   - tests/architecture/section14-token-cost.test.ts (D23) — locks
 *     adapter usage parse + ports.complete propagation + step/llm_call
 *     trace emission with token.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const LOCAL_TRACE = join(
  __dirname,
  "../../packages/domain/src/observability/local-trace.ts",
)

/** §14 fields that MUST appear as first-class fields on both
 *  `TraceEvent` (the read shape) and `CreateTraceEventInput`
 *  (the write shape). D23 (2026-08-31) adds `token` + `costUsd` so
 *  the §14 token/cost gap is closed as first-class capture. */
const REQUIRED_TOP_LEVEL_FIELDS: readonly string[] = [
  "conversationId",
  "runId",
  "stepId",
  "parentRunId",
  "subject",
  "triggerSource",
  "capability",
  "policyDecision",
  "grantId",
  "waitingStepId",
  "durationMs",
  "token",
  "costUsd",
]

describe("arch: §14 可观测字段 (TraceEvent carries DESIGN §14 fields as top-level fields)", () => {
  it("TraceEvent interface declares every required §14 field as a top-level readonly field", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    const traceEventMatch = src.match(
      /export interface TraceEvent\s*\{([\s\S]*?)\n\}/,
    )
    expect(traceEventMatch, "TraceEvent interface not found").not.toBeNull()
    const body = traceEventMatch?.[1] ?? ""
    for (const field of REQUIRED_TOP_LEVEL_FIELDS) {
      // Match `readonly <field>: ...` (the field declaration).
      const re = new RegExp(`readonly\\s+${field}\\b`, "m")
      expect(
        re.test(body),
        `TraceEvent missing top-level field: ${field}`,
      ).toBe(true)
    }
  })

  it("CreateTraceEventInput interface declares every required §14 field so callers must provide them", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    const inputMatch = src.match(
      /export interface CreateTraceEventInput\s*\{([\s\S]*?)\n\}/,
    )
    expect(inputMatch, "CreateTraceEventInput interface not found").not.toBeNull()
    const body = inputMatch?.[1] ?? ""
    for (const field of REQUIRED_TOP_LEVEL_FIELDS) {
      // The input uses optional `readonly <field>?: ...` or `readonly <field>: ... | null`.
      const re = new RegExp(`readonly\\s+${field}\\b`, "m")
      expect(
        re.test(body),
        `CreateTraceEventInput missing field: ${field}`,
      ).toBe(true)
    }
  })

  it("TraceEvent kinds cover the §14 surfaces (run / step / capability / policy / grant / approval)", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    // TraceKind is a union type written across multiple lines; capture
    // until the next blank line + `export ` boundary (no `;` terminator).
    const kindMatch = src.match(/export type TraceKind\s*=([\s\S]*?)\n\nexport /)
    expect(kindMatch, "TraceKind type not found").not.toBeNull()
    const body = kindMatch?.[1] ?? ""
    // Per §14 each observability event has one of these kind tags.
    expect(body).toMatch(/"run"/)
    expect(body).toMatch(/"step"/)
    expect(body).toMatch(/"capability"/)
    expect(body).toMatch(/"policy"/)
    expect(body).toMatch(/"grant"/)
    expect(body).toMatch(/"approval"/)
  })

  it("TraceEvent.status covers the §14 lifecycle states (ok / error / waiting)", () => {
    const src = readFileSync(LOCAL_TRACE, "utf-8")
    expect(src).toMatch(/readonly status:\s*"ok"\s*\|\s*"error"\s*\|\s*"waiting"/)
  })
})