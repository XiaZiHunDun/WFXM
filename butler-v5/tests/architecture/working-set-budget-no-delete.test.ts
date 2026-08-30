/**
 * Arch guard (D14-arch-align §20 #14): 模型输入是有预算的工作集；
 * 超预算只压缩工作集，不删除历史。
 *
 * DESIGN §20 invariant #14 mandates that working-set budget overrun
 * compresses the in-memory working set (kept + extractive summary) but
 * never deletes stored message history. This file locks that boundary.
 *
 * Static checks (no runtime):
 *   - `packages/runtime/src/working-set.ts` does NOT call any store
 *     mutation method (`create*`, `update*`, `delete*`, `transition*`,
 *     `append*`, `commit*`, `revoke*`). It is a pure transform.
 *   - `packages/runtime/src/working-set-budget.ts` does NOT call any
 *     store mutation method. `filterDevHistoryNoise` is a pure filter
 *     over its input array.
 *   - `packages/runtime/src/run-engine.ts` working-set assembly
 *     (between `store.listMessages` and the `buildWorkingSet` call)
 *     does NOT call any store mutation. The local `messages` variable
 *     must only be re-assigned (filter) — never persisted back.
 *   - `buildWorkingSet`, `splitBudget`, `extractiveSummary` are pure:
 *     they read `input.messages`, return new objects, never reach into
 *     a store / DB / Effect runtime.
 *
 * Runtime behavior is verified by:
 *   - packages/runtime/src/working-set.test.ts (12 messages budget /
 *     char budget / extractive summary / compacted flag)
 *   - packages/runtime/src/working-set-budget.test.ts (filterDevHistoryNoise
 *     keeps tail / drops ping/pwd noise)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const WORKING_SET = join(
  __dirname,
  "../../packages/runtime/src/working-set.ts",
)
const WORKING_SET_BUDGET = join(
  __dirname,
  "../../packages/runtime/src/working-set-budget.ts",
)
const RUN_ENGINE = join(
  __dirname,
  "../../packages/runtime/src/run-engine.ts",
)

// Any identifier that would mean the working-set layer reaches into
// persistence / DB / async effect runtime.
const STORE_MUTATION_PATTERNS: readonly RegExp[] = [
  /\bcreateScopedGrant\b/,
  /\bcreateMessage\b/,
  /\bcreateStep\b/,
  /\bupdateMessage\b/,
  /\bupdateStep\b/,
  /\bdeleteMessage\b/,
  /\btransitionRunStatus\b/,
  /\bappendConversationEvent\b/,
  /\bappendOutbox\b/,
  /\brevokeScopedGrants\b/,
  /\bcommit\b\s*\(/,
  /\bsave\w*\(/,
]

function hasMutation(src: string): readonly string[] {
  const hits: string[] = []
  for (const pattern of STORE_MUTATION_PATTERNS) {
    const match = src.match(pattern)
    if (match) hits.push(`${pattern.source} → ${match[0]}`)
  }
  return hits
}

describe("arch: working-set budget never deletes history (§20 #14)", () => {
  it("working-set.ts does NOT call any store / DB mutation API", () => {
    const src = readFileSync(WORKING_SET, "utf-8")
    const hits = hasMutation(src)
    expect(
      hits,
      `unexpected store-mutation calls in working-set.ts: ${hits.join(", ")}`,
    ).toEqual([])
  })

  it("working-set-budget.ts does NOT call any store / DB mutation API", () => {
    const src = readFileSync(WORKING_SET_BUDGET, "utf-8")
    const hits = hasMutation(src)
    expect(
      hits,
      `unexpected store-mutation calls in working-set-budget.ts: ${hits.join(", ")}`,
    ).toEqual([])
  })

  it("working-set.ts is pure (no async / no Effect / no fetch)", () => {
    const src = readFileSync(WORKING_SET, "utf-8")
    // The working-set transform must be a synchronous pure function.
    // No `await`, no `Effect.runPromise`, no `fetch`, no DB driver calls.
    expect(src).not.toMatch(/\bawait\b/)
    expect(src).not.toMatch(/\bEffect\b/)
    expect(src).not.toMatch(/\bfetch\b/)
  })

  it("working-set-budget.ts is pure (no async / no Effect / no fetch)", () => {
    const src = readFileSync(WORKING_SET_BUDGET, "utf-8")
    expect(src).not.toMatch(/\bawait\b/)
    expect(src).not.toMatch(/\bEffect\b/)
    expect(src).not.toMatch(/\bfetch\b/)
  })

  it("run-engine.ts working-set assembly chain does NOT mutate the store", () => {
    // Slice the run-engine file around the working-set assembly call:
    //   const messages = await this.store.listMessages(...)
    //   if (workingSetMode === "dev") { messages = filterDevHistoryNoise(messages) }
    //   const workingSet = buildWorkingSet({ messages, ..., budget: ... })
    // Any store.* mutation between listMessages and buildWorkingSet would
    // silently delete history. The slice between these two anchors must
    // contain no mutation API call.
    const src = readFileSync(RUN_ENGINE, "utf-8")
    const listMessagesMatch = src.match(/this\.store\.listMessages\(/g)
    expect(listMessagesMatch, "listMessages call not found in run-engine.ts").not.toBeNull()
    // Find the FIRST listMessages call and the nearest buildWorkingSet call
    // after it; the slice between must not contain any store mutation.
    const startIdx = src.indexOf("this.store.listMessages(")
    expect(startIdx).toBeGreaterThanOrEqual(0)
    const buildIdx = src.indexOf("buildWorkingSet(", startIdx)
    expect(buildIdx, "buildWorkingSet after listMessages not found").toBeGreaterThan(startIdx)
    const slice = src.slice(startIdx, buildIdx)
    // Allow filterDevHistoryNoise (pure filter) and resolveWorkingSetBudget
    // (env-only config). Disallow any other store / DB mutation.
    const hits = hasMutation(slice)
    expect(
      hits,
      `store mutation found between listMessages and buildWorkingSet: ${hits.join(", ")}`,
    ).toEqual([])
  })

  it("buildWorkingSet result contains `compacted: true` only when dropped messages were SUMMARIZED (not silently dropped)", () => {
    const src = readFileSync(WORKING_SET, "utf-8")
    // The compaction path must call extractiveSummary to fold dropped
    // messages into a single summary WorkingSetMessage — that is what
    // "compress working set" means. If the compaction branch returns
    // only the kept messages without the summary, the dropped messages
    // would be silently lost.
    expect(src).toMatch(/extractiveSummary\(dropped\)/)
    // The compacted branch must include extractiveSummary in its messages array.
    expect(src).toMatch(/\[?\s*\.\.\.prefix,\s*extractiveSummary\(dropped\),\s*\.\.\.kept/)
  })
})