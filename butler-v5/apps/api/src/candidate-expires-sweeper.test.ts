import { beforeEach, describe, expect, it } from "vitest"
import {
  parseCandidateExpiresSweeperConfig,
  runCandidateExpiresTick,
  startCandidateExpiresSweeperIfEnabled,
  type CandidateExpiresLogger,
} from "./candidate-expires-sweeper.js"

describe("parseCandidateExpiresSweeperConfig", () => {
  it("disabled by default", () => {
    expect(parseCandidateExpiresSweeperConfig({}).enabled).toBe(false)
  })

  it("enabled when BUTLER_V5_CANDIDATE_EXPIRES_ENABLED=1", () => {
    expect(
      parseCandidateExpiresSweeperConfig({
        BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: "1",
      }).enabled,
    ).toBe(true)
  })

  it("honours the shared 1/true/yes/on env convention", () => {
    for (const truthy of ["1", "true", "yes", "on"]) {
      expect(
        parseCandidateExpiresSweeperConfig({
          BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: truthy,
        }).enabled,
      ).toBe(true)
    }
    for (const falsy of ["0", "false", "off", ""]) {
      expect(
        parseCandidateExpiresSweeperConfig({
          BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: falsy,
        }).enabled,
      ).toBe(false)
    }
  })

  it("uses defaults for tickMs/ttlMs/batchLimit", () => {
    const cfg = parseCandidateExpiresSweeperConfig({
      BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: "1",
    })
    expect(cfg.tickMs).toBe(3_600_000)
    expect(cfg.ttlMs).toBe(7 * 24 * 3_600_000)
    expect(cfg.batchLimit).toBe(1000)
  })

  it("parses custom env values", () => {
    const cfg = parseCandidateExpiresSweeperConfig({
      BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: "1",
      BUTLER_V5_CANDIDATE_EXPIRES_INTERVAL_MS: "60000",
      BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS: "100000",
      BUTLER_V5_CANDIDATE_EXPIRES_BATCH_LIMIT: "50",
    })
    expect(cfg.tickMs).toBe(60_000)
    expect(cfg.ttlMs).toBe(100_000)
    expect(cfg.batchLimit).toBe(50)
  })
})

describe("startCandidateExpiresSweeperIfEnabled", () => {
  it("returns null when disabled", () => {
    const handle = startCandidateExpiresSweeperIfEnabled({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: {} as any,
      env: {},
    })
    expect(handle).toBeNull()
  })

  it("starts and stops cleanly when enabled", () => {
    const handle = startCandidateExpiresSweeperIfEnabled({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: { durableMemoryStore: {} } as any,
      env: { BUTLER_V5_CANDIDATE_EXPIRES_ENABLED: "1" },
      config: { enabled: true, tickMs: 10_000, ttlMs: 1000 },
    })
    expect(handle).not.toBeNull()
    handle?.stop()
  })
})

describe("runCandidateExpiresTick", () => {
  let infoCalls: string[]
  let errorCalls: string[]
  const logger: CandidateExpiresLogger = {
    info: (msg, ...args) => infoCalls.push(args.length > 0 ? `${msg} ${args.map(String).join(" ")}` : msg),
    error: (msg, ...args) => errorCalls.push(args.length > 0 ? `${msg} ${args.map(String).join(" ")}` : msg),
  }

  beforeEach(() => {
    infoCalls = []
    errorCalls = []
  })

  it("returns zeros when store returns no candidates", async () => {
    const wiring = {
      durableMemoryStore: {
        listExpiredCandidates: async () => [],
        markExpired: async () => [],
      },
    }
    const result = await runCandidateExpiresTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      ttlMs: 1000,
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.expired).toBe(0)
    expect(infoCalls).toHaveLength(1)
    expect(infoCalls[0]).toContain("scanned=0")
  })

  it("logs and returns zeros when store throws", async () => {
    const wiring = {
      durableMemoryStore: {
        listExpiredCandidates: async () => {
          throw new Error("db down")
        },
        markExpired: async () => [],
      },
    }
    const result = await runCandidateExpiresTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      ttlMs: 1000,
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.expired).toBe(0)
    expect(errorCalls).toHaveLength(1)
    expect(errorCalls[0]).toContain("tick failed")
    expect(errorCalls[0]).toContain("db down")
  })

  it("logs and returns zeros when store not wired", async () => {
    const wiring = { durableMemoryStore: null }
    const result = await runCandidateExpiresTick({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test stub
      wiring: wiring as any,
      ttlMs: 1000,
      logger,
      now: () => new Date(1000),
    })
    expect(result.scanned).toBe(0)
    expect(result.expired).toBe(0)
    expect(errorCalls).toHaveLength(1)
    expect(errorCalls[0]).toContain("not wired")
  })
})