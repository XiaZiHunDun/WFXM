import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  runAutoPromoteTick,
  startAutoPromoteSweeperIfEnabled,
  type AutoPromoteLogger,
} from "./auto-promote-sweeper.js"

describe("startAutoPromoteSweeperIfEnabled", () => {
  it("returns null when disabled", () => {
    const handle = startAutoPromoteSweeperIfEnabled({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: {} as any,
      config: {
        enabled: false,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 10_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
    })
    expect(handle).toBeNull()
  })

  it("starts and stops cleanly when enabled", () => {
    const handle = startAutoPromoteSweeperIfEnabled({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: { durableMemoryStore: {} } as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 10_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
    })
    expect(handle).not.toBeNull()
    handle?.stop()
  })

  // D58 T3 (audit #1 F-07): stop() must not leak a setTimeout that
  // would re-enter tick() after the sweeper is supposedly halted. With
  // fake timers we can hold the in-flight tick open, call stop(), then
  // observe whether a fresh setTimeout was scheduled.
  it("stop() does not leave a pending setTimeout that re-fires tick", async () => {
    vi.useFakeTimers()
    try {
      const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout")
      let resolveTick: (() => void) | null = null
      const wiring = {
        durableMemoryStore: {
          findAutoPromoteCandidates: () =>
            new Promise<readonly unknown[]>((resolve) => {
              // Hold the in-flight tick open so stop() races with it.
              resolveTick = () => resolve([])
            }),
          markAutoPromoted: async () => 0,
        },
      }
      const handle = startAutoPromoteSweeperIfEnabled({
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
        wiring: wiring as any,
        config: {
          enabled: true,
          windowMs: 1000,
          sweepLimit: 500,
          sweepIntervalMs: 100,
          rollbackWindowMs: 7 * 24 * 3_600_000,
        },
      })
      expect(handle).not.toBeNull()
      // Let the first tick start (microtasks only — fake timers hold setTimeout).
      await vi.advanceTimersByTimeAsync(0)
      // Call stop() while tick is still awaiting.
      handle?.stop()
      const setTimeoutCallsAtStop = setTimeoutSpy.mock.calls.length
      // Release the in-flight tick and let any scheduled timer attempt to fire.
      if (resolveTick) resolveTick()
      await vi.advanceTimersByTimeAsync(500)
      // After stop(), no NEW setTimeout should have been scheduled by the
      // sweeper (post-await path must observe `stopped === true`).
      expect(setTimeoutSpy.mock.calls.length).toBe(setTimeoutCallsAtStop)
    } finally {
      vi.useRealTimers()
      vi.restoreAllMocks()
    }
  })
})

describe("runAutoPromoteTick", () => {
  let infoCalls: string[]
  let errorCalls: string[]
  const logger: AutoPromoteLogger = {
    info: (msg, ...args) =>
      infoCalls.push(args.length > 0 ? `${msg} ${args.map(String).join(" ")}` : msg),
    error: (msg, ...args) =>
      errorCalls.push(args.length > 0 ? `${msg} ${args.map(String).join(" ")}` : msg),
  }

  beforeEach(() => {
    infoCalls = []
    errorCalls = []
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns zeros when store returns no candidates", async () => {
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => [],
        markAutoPromoted: async () => 0,
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.promoted).toBe(0)
    expect(infoCalls).toHaveLength(1)
    expect(infoCalls[0]).toContain("scanned=0")
  })

  it("logs and returns zeros when store throws", async () => {
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => {
          throw new Error("db down")
        },
        markAutoPromoted: async () => 0,
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.promoted).toBe(0)
    expect(errorCalls).toHaveLength(1)
    expect(errorCalls[0]).toContain("tick failed")
    expect(errorCalls[0]).toContain("db down")
  })

  it("logs and returns zeros when store not wired", async () => {
    const wiring = {
      durableMemoryStore: null,
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: { enabled: true, windowMs: 1000, sweepLimit: 500, sweepIntervalMs: 3_600_000, rollbackWindowMs: 7 * 24 * 3_600_000 },
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.promoted).toBe(0)
    expect(errorCalls).toHaveLength(1)
    expect(errorCalls[0]).toContain("not wired")
  })

  it("calls markAutoPromoted with toPromote ids and logs count", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => [
          { id: "id-1", subject: "owner", content: "x", createdAt: new Date(baseMs) },
          { id: "id-2", subject: "owner", content: "y", createdAt: new Date(baseMs + 1000) },
        ],
        markAutoPromoted: vi.fn(async () => 2),
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(baseMs + 10_000),
    })
    expect(result.scanned).toBe(2)
    expect(result.promoted).toBe(2)
    expect(wiring.durableMemoryStore.markAutoPromoted).toHaveBeenCalledWith({
      ids: ["id-1", "id-2"],
      now: new Date(baseMs + 10_000),
    })
    expect(infoCalls[0]).toContain("promoted=2")
  })

  it("is idempotent across multiple cycles", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    let callCount = 0
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => {
          callCount++
          // First call: returns 2 candidates; second call: 0 (already promoted)
          return callCount === 1
            ? [
                { id: "id-1", subject: "owner", content: "x", createdAt: new Date(baseMs) },
                { id: "id-2", subject: "owner", content: "y", createdAt: new Date(baseMs + 1000) },
              ]
            : []
        },
        markAutoPromoted: async () => 2,
      },
    }
    const cfg = {
      enabled: true,
      windowMs: 1000,
      sweepLimit: 500,
      sweepIntervalMs: 3_600_000,
      rollbackWindowMs: 7 * 24 * 3_600_000,
    }
    const r1 = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: cfg,
      logger,
      now: () => new Date(baseMs + 10_000),
    })
    expect(r1.promoted).toBe(2)
    const r2 = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: cfg,
      logger,
      now: () => new Date(baseMs + 20_000),
    })
    expect(r2.promoted).toBe(0)
  })

  // D56 audit F13 (must-fix): notify hook was never covered. The C 方向
  // sweeper-notify architecture assumes both sweepers call notify when they
  // promote — candidate-expires has notify coverage (D55 SF-04), auto-promote
  // had none. These three cases pin the contract:
  //   1. notify NOT called when nothing promoted
  //   2. notify called exactly once with {promoted, scanned} when promoted > 0
  //   3. notify throw is caught + logged + tick still returns its stats
  it("does NOT call notify when promoted=0", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const notify = vi.fn(async () => undefined)
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => [],
        markAutoPromoted: async () => 0,
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(baseMs + 10_000),
      notify,
    })
    expect(result.promoted).toBe(0)
    expect(notify).not.toHaveBeenCalled()
  })

  it("calls notify once with {promoted, scanned} when promoted > 0", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const notify = vi.fn(async () => undefined)
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => [
          { id: "id-1", subject: "owner", content: "x", createdAt: new Date(baseMs) },
          { id: "id-2", subject: "owner", content: "y", createdAt: new Date(baseMs + 1000) },
        ],
        markAutoPromoted: async () => 2,
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(baseMs + 10_000),
      notify,
    })
    expect(result.promoted).toBe(2)
    expect(result.scanned).toBe(2)
    expect(notify).toHaveBeenCalledTimes(1)
    expect(notify).toHaveBeenCalledWith(
      expect.objectContaining({ promoted: 2, scanned: 2 }),
    )
  })

  it("catches notify throw, logs error, still returns tick stats", async () => {
    const baseMs = Date.parse("2026-09-01T00:00:00Z")
    const notify = vi.fn(async () => {
      throw new Error("wechat push down")
    })
    const wiring = {
      durableMemoryStore: {
        findAutoPromoteCandidates: async () => [
          { id: "id-1", subject: "owner", content: "x", createdAt: new Date(baseMs) },
        ],
        markAutoPromoted: async () => 1,
      },
    }
    const result = await runAutoPromoteTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      config: {
        enabled: true,
        windowMs: 1000,
        sweepLimit: 500,
        sweepIntervalMs: 3_600_000,
        rollbackWindowMs: 7 * 24 * 3_600_000,
      },
      logger,
      now: () => new Date(baseMs + 10_000),
      notify,
    })
    expect(result.promoted).toBe(1)
    expect(result.scanned).toBe(1)
    expect(notify).toHaveBeenCalledTimes(1)
    // notify throw must not break the sweep; tick still returns stats.
    expect(errorCalls.some((m) => m.includes("notify failed"))).toBe(true)
    expect(errorCalls.some((m) => m.includes("wechat push down"))).toBe(true)
  })
})
