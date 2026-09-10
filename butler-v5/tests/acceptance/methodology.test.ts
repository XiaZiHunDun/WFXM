/**
 * D53a methodology verifier — 验证协议本身可执行。
 * 这些 test 是 meta-test, 验证 runMultiRound / aggregate / baseline / ship-claim / env 的实现契约。
 * No dependency on 41 acceptance scenarios; pure unit test of the protocol layer.
 */
import { describe, expect, it } from "vitest"
import {
  runMultiRound,
  aggregateResults,
  compareBaseline,
  renderShipClaim,
  readMultiRoundEnv,
} from "./multi-round.js"
import { readFileSync, existsSync } from "node:fs"
import { join } from "node:path"

describe("D53a methodology", () => {
  describe("runMultiRound", () => {
    it("runs fn N times and returns all results", async () => {
      let calls = 0
      const result = await runMultiRound(
        async () => {
          calls += 1
        },
        { rounds: 3, aggregation: "all" },
      )
      expect(calls).toBe(3)
      expect(result.rounds).toHaveLength(3)
      expect(result.passed).toBe(true)
    })

    it("fails when any round fails (aggregation=all)", async () => {
      const result = await runMultiRound(
        async () => {
          throw new Error("flake")
        },
        { rounds: 3, aggregation: "all" },
      )
      expect(result.passed).toBe(false)
      expect(result.rounds.filter((r) => !r.passed)).toHaveLength(3)
    })

    it("passes when >=2/3 rounds pass (aggregation=majority)", async () => {
      let count = 0
      const result = await runMultiRound(
        async () => {
          count += 1
          if (count === 2) throw new Error("flake once")
        },
        { rounds: 3, aggregation: "majority" },
      )
      expect(result.passed).toBe(true)
      expect(result.rounds.filter((r) => r.passed)).toHaveLength(2)
    })
  })

  describe("aggregateResults", () => {
    it("all: requires all rounds pass", () => {
      const all = aggregateResults(
        [
          { passed: true },
          { passed: true },
          { passed: false },
        ],
        "all",
      )
      expect(all).toBe(false)
    })

    it("majority: requires >=ceil(N/2) pass", () => {
      const m = aggregateResults(
        [
          { passed: true },
          { passed: false },
          { passed: true },
        ],
        "majority",
      )
      expect(m).toBe(true)
    })
  })

  describe("compareBaseline", () => {
    it("detects status change as critical (when baseline.status > 0)", () => {
      const diff = compareBaseline(
        { A1: { status: 201, replyLen: 100, toolCalls: 1, approvalCount: 0 } },
        { A1: { status: 500, replyLen: 100, toolCalls: 1, approvalCount: 0 } },
      )
      const critical = diff.find((d) => d.field === "status" && d.severity === "critical")
      expect(critical).toBeDefined()
    })

    it("skips status comparison when baseline.status is 0 (placeholder)", () => {
      const diff = compareBaseline(
        { A1: { status: 0, replyLen: 100, toolCalls: 1, approvalCount: 0 } },
        { A1: { status: 201, replyLen: 100, toolCalls: 1, approvalCount: 0 } },
      )
      const statusDiff = diff.find((d) => d.field === "status")
      expect(statusDiff).toBeUndefined()
    })

    it("flags replyLen drift >=50% as info", () => {
      const diff = compareBaseline(
        { A1: { status: 201, replyLen: 100, toolCalls: 1, approvalCount: 0 } },
        { A1: { status: 201, replyLen: 200, toolCalls: 1, approvalCount: 0 } },
      )
      const info = diff.find((d) => d.field === "replyLen" && d.severity === "info")
      expect(info).toBeDefined()
    })
  })

  describe("renderShipClaim", () => {
    it("includes '本 ship' marker (D50 lesson)", () => {
      const text = renderShipClaim({
        shipEvent: "D53a",
        date: "2026-09-10",
        testResults: { methodology: "10/10", acceptance: "41/41", full: "1862+20/1862+20" },
      })
      expect(text).toContain("本 ship")
      expect(text).toContain("D53a")
      expect(text).toContain("2026-09-10")
    })
  })

  describe("readMultiRoundEnv", () => {
    it("defaults to rounds=3 aggregation=all when env unset", () => {
      const prev1 = process.env.BUTLER_V5_MULTI_ROUND
      const prev2 = process.env.BUTLER_V5_AGGREGATION
      delete process.env.BUTLER_V5_MULTI_ROUND
      delete process.env.BUTLER_V5_AGGREGATION
      try {
        const env = readMultiRoundEnv()
        expect(env.rounds).toBe(3)
        expect(env.aggregation).toBe("all")
      } finally {
        if (prev1 !== undefined) process.env.BUTLER_V5_MULTI_ROUND = prev1
        if (prev2 !== undefined) process.env.BUTLER_V5_AGGREGATION = prev2
      }
    })

    it("honors BUTLER_V5_MULTI_ROUND=0 (opt-out, 1 round)", () => {
      const prev = process.env.BUTLER_V5_MULTI_ROUND
      process.env.BUTLER_V5_MULTI_ROUND = "0"
      try {
        const env = readMultiRoundEnv()
        expect(env.rounds).toBe(1)
      } finally {
        if (prev !== undefined) process.env.BUTLER_V5_MULTI_ROUND = prev
        else delete process.env.BUTLER_V5_MULTI_ROUND
      }
    })

    it("honors BUTLER_V5_AGGREGATION=majority", () => {
      const prev = process.env.BUTLER_V5_AGGREGATION
      process.env.BUTLER_V5_AGGREGATION = "majority"
      try {
        const env = readMultiRoundEnv()
        expect(env.aggregation).toBe("majority")
      } finally {
        if (prev !== undefined) process.env.BUTLER_V5_AGGREGATION = prev
        else delete process.env.BUTLER_V5_AGGREGATION
      }
    })
  })

  describe("baseline file present", () => {
    it("D53a baseline JSON exists at expected path with 35 scenarios", () => {
      const path = join(
        import.meta.dirname ?? ".",
        "recordings",
        ".baseline-2026-09-10.json",
      )
      expect(existsSync(path)).toBe(true)
      const data = JSON.parse(readFileSync(path, "utf8"))
      expect(data.shipEvent).toBe("D53a")
      expect(data.snapshotDate).toBe("2026-09-10")
      // Task 2 drift: recordings/ 实际是 35 scenarios (A1-A10, B1-B10, C1-C10, D1-D5 = 10+10+10+5)
      // realistic test 有 41 (35 + 5 D52 + 1 A11) 但 recordings/ 没更新, D53c 重新评估时处理
      expect(Object.keys(data.scenarios).length).toBe(35)
    })
  })
})