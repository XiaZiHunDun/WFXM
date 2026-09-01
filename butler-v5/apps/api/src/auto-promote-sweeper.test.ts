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
})
