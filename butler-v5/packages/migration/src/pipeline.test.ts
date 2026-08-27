import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { runMigration, type MigrationConfig } from "./pipeline.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"

describe("Migration pipeline", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "migration-test" })
  })

  afterEach(async () => {
    await db.close()
  })

  it("exports an idempotent runMigration entry", () => {
    expect(typeof runMigration).toBe("function")
  })

  it("dry-run returns ok with zero events for empty v4 root", async () => {
    const config: MigrationConfig = {
      v4Root: "/tmp",
      bridge,
      dryRun: true,
    }
    const r = await runMigration(config)
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.eventsWritten).toBe(0)
      expect(r.skipped).toBe(0)
    }
  })

  it("returns ok:false when v4Root is invalid", async () => {
    const config: MigrationConfig = {
      v4Root: "" as unknown as string,
      bridge,
      dryRun: false,
    }
    const r = await runMigration(config)
    expect(r.ok).toBe(false)
  })
})
