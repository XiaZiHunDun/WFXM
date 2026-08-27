import { describe, expect, it } from "vitest"
import { fixedClock, systemClock } from "./clock.js"
import type { ClockPort } from "./clock.js"

describe("ClockPort", () => {
  it("systemClock.now returns a fresh Date on each call", () => {
    expect(systemClock.now()).toBeInstanceOf(Date)
    // 两次调用返回不同实例（系统时钟推进）
    const a = systemClock.now()
    const b = systemClock.now()
    expect(a).not.toBe(b)
  })

  it("fixedClock.now returns the same instant deterministically", () => {
    const at = new Date("2026-05-01T08:00:00Z")
    const clock: ClockPort = fixedClock(at)
    expect(clock.now()).toBe(at)
    expect(clock.now()).toBe(at)
    expect(clock.now().getTime()).toBe(at.getTime())
  })
})