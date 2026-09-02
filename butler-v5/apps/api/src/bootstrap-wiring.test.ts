import { describe, expect, it } from "vitest"
import { createProductionWiring } from "./bootstrap-wiring.js"

describe("createProductionWiring (Composition Root)", () => {
  it("returns { ok: false } with a reason instead of throwing when the DB cannot open", async () => {
    // BUTLER_V5_DB=postgres with no DATABASE_URL is a deterministic, side-effect-free
    // failure inside openButlerDatabase (which never throws by contract).
    const result = await createProductionWiring({ BUTLER_V5_DB: "postgres" })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.reason).toContain("DATABASE_URL")
    }
  })
})
