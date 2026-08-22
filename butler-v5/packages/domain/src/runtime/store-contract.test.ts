import { describe, expect, it } from "vitest"
import {
  DEFAULT_READ_MODEL_SOURCE,
  resolveReadModelSource,
} from "./store-contract.js"

describe("resolveReadModelSource", () => {
  it("defaults to relational when env is unset", () => {
    expect(DEFAULT_READ_MODEL_SOURCE).toBe("relational")
    expect(resolveReadModelSource({})).toBe("relational")
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: undefined })).toBe("relational")
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: "" })).toBe("relational")
  })

  it("accepts explicit event_store | hybrid | relational", () => {
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: "event_store" })).toBe("event_store")
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: "HYBRID" })).toBe("hybrid")
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: " relational " })).toBe("relational")
  })

  it("falls back to relational for unknown values", () => {
    expect(resolveReadModelSource({ BUTLER_V5_READ_MODEL: "legacy" })).toBe("relational")
  })
})
