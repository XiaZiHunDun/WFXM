import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { saveSnapshot, loadSnapshot } from "./snapshot.js"
import { makeTestDb } from "./testing.js"

describe("snapshot", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  beforeEach(async () => {
    db = await makeTestDb()
  })
  afterEach(async () => {
    await db.close()
  })

  it("saves and loads a snapshot for a stream", async () => {
    await saveSnapshot(db.db, "s-1", 5, { count: 3 })
    const loaded = await loadSnapshot(db.db, "s-1")
    expect(loaded?.streamVersion).toBe(5)
    expect(loaded?.payload).toEqual({ count: 3 })
  })

  it("overwrites an older snapshot for the same stream", async () => {
    await saveSnapshot(db.db, "s-1", 3, { v: 3 })
    await saveSnapshot(db.db, "s-1", 7, { v: 7 })
    const loaded = await loadSnapshot(db.db, "s-1")
    expect(loaded?.streamVersion).toBe(7)
    expect(loaded?.payload).toEqual({ v: 7 })
  })

  it("returns null for a stream with no snapshot", async () => {
    const loaded = await loadSnapshot(db.db, "s-missing")
    expect(loaded).toBeNull()
  })
})
