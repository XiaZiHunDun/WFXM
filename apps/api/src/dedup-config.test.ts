import { describe, expect, it } from "vitest"
import { parseDedupConfig } from "./dedup-config.js"

describe("parseDedupConfig", () => {
  it("default threshold 0.85 enabled, recent 90d, limit 50", () => {
    const cfg = parseDedupConfig({})
    expect(cfg.enabled).toBe(true)
    expect(cfg.threshold).toBe(0.85)
    expect(cfg.recentMs).toBe(90 * 24 * 3_600_000)
    expect(cfg.limit).toBe(50)
  })

  it("threshold=0 disables dedup", () => {
    const cfg = parseDedupConfig({ BUTLER_V5_MEMORY_DEDUP_THRESHOLD: "0" })
    expect(cfg.enabled).toBe(false)
    expect(cfg.threshold).toBe(0)
  })

  it("parses custom env values", () => {
    const cfg = parseDedupConfig({
      BUTLER_V5_MEMORY_DEDUP_THRESHOLD: "0.92",
      BUTLER_V5_MEMORY_DEDUP_RECENT_MS: "604800000", // 7d
      BUTLER_V5_MEMORY_DEDUP_LIMIT: "100",
    })
    expect(cfg.threshold).toBe(0.92)
    expect(cfg.recentMs).toBe(604_800_000)
    expect(cfg.limit).toBe(100)
  })
})
