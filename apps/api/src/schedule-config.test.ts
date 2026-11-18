import { describe, expect, it } from "vitest"
import {
  isScheduleEnabled,
  parseScheduleJobsJson,
  parseScheduleWorkerConfig,
} from "./schedule-config.js"

describe("schedule-config", () => {
  it("parses job JSON with defaults", () => {
    const jobs = parseScheduleJobsJson(
      JSON.stringify([
        { id: "hb", goal: "巡检", everyMs: 60_000 },
        { id: "", goal: "bad" },
      ]),
    )
    expect(jobs).toHaveLength(1)
    expect(jobs[0]).toMatchObject({
      id: "hb",
      goal: "巡检",
      everyMs: 60_000,
      quietSuccess: true,
      enabled: true,
      maxSteps: 3,
    })
  })

  it("reads enablement and tick from env", () => {
    expect(isScheduleEnabled({})).toBe(false)
    expect(isScheduleEnabled({ BUTLER_V5_SCHEDULE_ENABLED: "1" })).toBe(true)
    const cfg = parseScheduleWorkerConfig({
      BUTLER_V5_SCHEDULE_ENABLED: "1",
      BUTLER_V5_SCHEDULE_TICK_MS: "5000",
      BUTLER_V5_SCHEDULE_JOBS: JSON.stringify([{ id: "a", goal: "g", everyMs: 1000 }]),
      BUTLER_V5_SCHEDULE_DEFER_WHEN_BUSY: "yes",
    })
    expect(cfg.enabled).toBe(true)
    expect(cfg.tickMs).toBe(5000)
    expect(cfg.deferWhenMainBusy).toBe(true)
    expect(cfg.jobs).toHaveLength(1)
  })
})
