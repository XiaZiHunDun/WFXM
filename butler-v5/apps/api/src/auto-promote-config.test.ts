import { describe, expect, it } from "vitest"
import { parseAutoPromoteConfig } from "./auto-promote-config.js"

describe("parseAutoPromoteConfig", () => {
  it("disabled by default", () => {
    const cfg = parseAutoPromoteConfig({})
    expect(cfg.enabled).toBe(false)
  })

  it("enabled when BUTLER_V5_AUTO_PROMOTE_ENABLED=1", () => {
    const cfg = parseAutoPromoteConfig({ BUTLER_V5_AUTO_PROMOTE_ENABLED: "1" })
    expect(cfg.enabled).toBe(true)
  })

  it("uses defaults for windowMs / sweepLimit / sweepIntervalMs / rollbackWindowMs", () => {
    const cfg = parseAutoPromoteConfig({ BUTLER_V5_AUTO_PROMOTE_ENABLED: "1" })
    expect(cfg.windowMs).toBe(3 * 24 * 3_600_000)
    expect(cfg.sweepLimit).toBe(500)
    expect(cfg.sweepIntervalMs).toBe(6 * 3_600_000)
    expect(cfg.rollbackWindowMs).toBe(7 * 24 * 3_600_000)
  })

  it("parses custom env values", () => {
    const cfg = parseAutoPromoteConfig({
      BUTLER_V5_AUTO_PROMOTE_ENABLED: "1",
      BUTLER_V5_AUTO_PROMOTE_WINDOW_DAYS: "1",
      BUTLER_V5_AUTO_PROMOTE_SWEEP_LIMIT: "100",
      BUTLER_V5_AUTO_PROMOTE_SWEEP_INTERVAL_HOURS: "12",
      BUTLER_V5_AUTO_PROMOTE_ROLLBACK_WINDOW_DAYS: "14",
    })
    expect(cfg.windowMs).toBe(24 * 3_600_000)
    expect(cfg.sweepLimit).toBe(100)
    expect(cfg.sweepIntervalMs).toBe(12 * 3_600_000)
    expect(cfg.rollbackWindowMs).toBe(14 * 24 * 3_600_000)
  })
})
