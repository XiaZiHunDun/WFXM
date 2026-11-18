import { describe, expect, it } from "vitest"
import { getTableName } from "drizzle-orm"
import { eventStore, outbox, snapshots, projections } from "./schema.js"

describe("R3.0 sanity", () => {
  it("schema exports are defined", () => {
    expect(eventStore).toBeDefined()
    expect(outbox).toBeDefined()
    expect(snapshots).toBeDefined()
    expect(projections).toBeDefined()
  })

  it("table names match plan", () => {
    expect(getTableName(eventStore)).toBe("event_store")
    expect(getTableName(outbox)).toBe("outbox")
    expect(getTableName(snapshots)).toBe("snapshots")
    expect(getTableName(projections)).toBe("projections")
  })
})
