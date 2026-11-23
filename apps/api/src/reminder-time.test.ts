import { describe, expect, it } from "vitest"
import {
  formatReminderSchedule,
  formatReminderTime,
  nextReminderFireAtMs,
  parseReminderTime,
} from "./reminder-time.js"

// 2026-11-23 12:00 Asia/Shanghai.
const NOW = Date.UTC(2026, 10, 23, 4, 0)
const TOMORROW_0930 = Date.UTC(2026, 10, 24, 1, 30)

describe("parseReminderTime", () => {
  it("parses Asia/Shanghai local time", () => {
    const result = parseReminderTime({
      text: "2026-11-24 09:30",
      repeat: "once",
      nowMs: NOW,
    })
    expect(result).toEqual({ ok: true, fireAtMs: TOMORROW_0930 })
  })

  it("accepts T separator, seconds and explicit offsets", () => {
    for (const text of [
      "2026-11-24T09:30",
      "2026-11-24 09:30:00",
      "2026-11-24T09:30:00+08:00",
      "2026-11-24T01:30:00Z",
    ]) {
      expect(parseReminderTime({ text, repeat: "once", nowMs: NOW })).toEqual({
        ok: true,
        fireAtMs: TOMORROW_0930,
      })
    }
  })

  it("rejects impossible dates instead of silently normalizing", () => {
    expect(parseReminderTime({ text: "2026-02-30 09:00", repeat: "once", nowMs: NOW }).ok).toBe(
      false,
    )
    expect(parseReminderTime({ text: "2026-11-24 25:00", repeat: "once", nowMs: NOW }).ok).toBe(
      false,
    )
    expect(parseReminderTime({ text: "明天早上", repeat: "once", nowMs: NOW }).ok).toBe(false)
  })

  it("rejects past once reminders", () => {
    const result = parseReminderTime({
      text: "2026-11-23 08:00",
      repeat: "once",
      nowMs: NOW,
    })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain("已过去")
  })

  it("rolls past daily/weekly times forward", () => {
    const daily = parseReminderTime({
      text: "2026-11-23 08:00",
      repeat: "daily",
      nowMs: NOW,
    })
    expect(daily).toEqual({ ok: true, fireAtMs: Date.UTC(2026, 10, 24, 0, 0) })

    const weekly = parseReminderTime({
      text: "2026-11-16 08:00",
      repeat: "weekly",
      nowMs: NOW,
    })
    expect(weekly).toEqual({ ok: true, fireAtMs: Date.UTC(2026, 10, 30, 0, 0) })
  })
})

describe("formatReminderTime / schedule", () => {
  it("formats in Asia/Shanghai", () => {
    expect(formatReminderTime(TOMORROW_0930)).toBe("2026-11-24 09:30")
    expect(formatReminderSchedule(TOMORROW_0930, "once")).toBe("2026-11-24 09:30")
    expect(formatReminderSchedule(TOMORROW_0930, "daily")).toBe("每天 09:30")
    expect(formatReminderSchedule(TOMORROW_0930, "weekly")).toMatch(/^每周[一二三四五六日] 09:30$/)
  })

  it("advances recurring reminders", () => {
    expect(nextReminderFireAtMs(TOMORROW_0930, "once")).toBeUndefined()
    expect(nextReminderFireAtMs(TOMORROW_0930, "daily")).toBe(TOMORROW_0930 + 86_400_000)
    expect(nextReminderFireAtMs(TOMORROW_0930, "weekly")).toBe(TOMORROW_0930 + 7 * 86_400_000)
  })
})
