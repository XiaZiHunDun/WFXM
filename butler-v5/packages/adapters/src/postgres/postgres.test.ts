import { describe, expect, it } from "vitest"
import { makePostgresAdapters } from "./index.js"

describe("Postgres adapters", () => {
  it("builds without a real db (skeleton wires ports)", () => {
    // Adapter factory must produce a layer bundle even when db is null,
    // so downstream config validation can fail fast without I/O.
    const adapter = makePostgresAdapters({
      db: null as unknown as Parameters<typeof makePostgresAdapters>[0]["db"],
    })
    expect(adapter.eventStore).toBeDefined()
    expect(adapter.outbox).toBeDefined()
    expect(adapter.snapshot).toBeDefined()
    expect(adapter.projection).toBeDefined()
  })
})
