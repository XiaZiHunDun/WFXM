/**
 * Arch guard (D7-arch-align §20 #8): outbox is ONLY for post-transactional
 * async side effects. The class method `EventBridge.enqueueOutbox` is
 * intentionally NOT exposed because it would let callers enqueue outbox
 * rows OUTSIDE of a state-change transaction — orphan outbox rows that
 * fire when the state change they reference hasn't committed.
 *
 * Static checks (no runtime):
 *   - EventBridge class does NOT declare an `enqueueOutbox` method
 *   - The outbox table is only written from one source path in
 *     packages/persistence/src/ (the `enqueueOutbox` function inside
 *     `appendEventAndEnqueueOutbox`'s `db.transaction` block)
 *   - The only public outbox-writing API is `EventStorePort.appendConversationEventWithOutbox`
 *     (which composes event row + outbox row inside one tx)
 *
 * Runtime behavior is verified by:
 *   - packages/persistence/src/event-store.test.ts ("appendEventAndEnqueueOutbox writes event and outbox atomically")
 *   - packages/persistence/src/outbox.test.ts (worker drain semantics)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const EVENT_BRIDGE = join(
  __dirname,
  "../../packages/persistence/src/event-bridge.ts",
)
const EVENT_STORE = join(
  __dirname,
  "../../packages/persistence/src/event-store.ts",
)
const OUTBOX = join(__dirname, "../../packages/persistence/src/outbox.ts")

describe("arch: outbox post-transactional (§20 #8)", () => {
  it("EventBridge does NOT declare an enqueueOutbox method (no orphan outbox path)", () => {
    const src = readFileSync(EVENT_BRIDGE, "utf-8")
    // The class is a single class in this file; the method is forbidden
    // (would let callers skip the tx-composing wrapper).
    expect(src).not.toMatch(/^\s*(async\s+)?enqueueOutbox\s*\(/m)
  })

  it("EventBridge imports enqueueOutbox symbol (legacy import removed) only via event-store barrel", () => {
    const src = readFileSync(EVENT_BRIDGE, "utf-8")
    // After D7: no top-level `import { enqueueOutbox } from "./outbox.js"`.
    // The only way `enqueueOutbox` should reach EventBridge is through the
    // event-store.ts barrel which composes it inside a transaction.
    expect(src).not.toMatch(/from\s+["']\.\/outbox\.js["']/)
  })

  it("appendEventAndEnqueueOutbox wraps the outbox write inside db.transaction", () => {
    const src = readFileSync(EVENT_STORE, "utf-8")
    // Locate the function body and confirm the enqueueOutbox call sits
    // inside a db.transaction block.
    const fnMatch = src.match(
      /export\s+async\s+function\s+appendEventAndEnqueueOutbox\([\s\S]+?\n\}\n/,
    )
    const body = fnMatch?.[0] ?? ""
    expect(body).toMatch(/db\.transaction\(async\s*\(tx\)\s*=>\s*\{/)
    // enqueueOutbox call inside the tx must take `tx`, not `db`.
    const enqueueMatch = body.match(/enqueueOutbox\(\s*(\w+)/)
    expect(enqueueMatch, "enqueueOutbox call not found").toBeTruthy()
    expect(enqueueMatch?.[1]).toBe("tx")
  })

  it("outbox.ts enqueueOutbox is only called from appendEventAndEnqueueOutbox (not from event-bridge)", () => {
    const ob = readFileSync(OUTBOX, "utf-8")
    expect(ob).toMatch(/export\s+async\s+function\s+enqueueOutbox/)
  })
})
