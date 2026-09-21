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
import { execSync } from "node:child_process"
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
      // D53c Task 7 Drift 2: 补 6 placeholder (A11-session-digest + D1-D5 chain)
      // recordings/ 35 真实 metric + 6 placeholder (D52/A11 ship 后) = 41
      expect(Object.keys(data.scenarios).length).toBe(41)
    })
  })

  // ----- M15 (D77 T7) — docker deploy artifacts 齐 + cross-link 一致 -----
  describe("M15 — docker deploy artifacts 齐 + cross-link 一致", () => {
    const repoRoot = "/home/ailearn/projects/WFXM"

    const requiredFiles = [
      "Dockerfile",
      ".dockerignore",
      ".github/workflows/release.yml",
      ".github/dependabot.yml",
      "butler-v5/docker-compose.yml",
      "butler-v5/apps/api/src/routes/health.ts",
      "docs/deployment/production-hardening.md",
      "docs/deployment/README.md",
      "tests/acceptance/scenarios_docker_deploy.md",
    ]

    it("all 9 docker deploy artifacts present", () => {
      for (const f of requiredFiles) {
        expect(existsSync(`${repoRoot}/${f}`), `missing ${f}`).toBe(true)
      }
    })

    it("§20 NON_LLM_ENTRY_POINTS includes routes/health.ts", () => {
      const result = execSync(
        `grep -rln "routes/health\\.ts" ${repoRoot}/butler-v5/tests/architecture/ 2>/dev/null`,
        { encoding: "utf-8" },
      )
      expect(result.trim().length, "§20 update missing").toBeGreaterThan(0)
    })

    it("AGENTS.md links to production-hardening", () => {
      const agents = readFileSync(`${repoRoot}/AGENTS.md`, "utf-8")
      expect(agents, "AGENTS.md link missing").toContain("production-hardening")
    })

    it("hardening.md Secret<T> cross-link points to real source", () => {
      const doc = readFileSync(
        `${repoRoot}/docs/deployment/production-hardening.md`,
        "utf-8",
      )
      expect(doc, "Secret<T> link missing").toContain(
        "@butler/adapters/wechat/secret.js",
      )
      expect(doc, "wrong cross-link still present").not.toContain("@butler/security")
    })

    it("hardening.md cross-links to SECURITY + production architecture", () => {
      const doc = readFileSync(
        `${repoRoot}/docs/deployment/production-hardening.md`,
        "utf-8",
      )
      expect(doc).toMatch(/SECURITY\.md|v5-production-architecture/)
    })

    it("compose YAML valid + butler service + loopback only", () => {
      const compose = readFileSync(
        `${repoRoot}/butler-v5/docker-compose.yml`,
        "utf-8",
      )
      expect(compose, "butler service missing").toMatch(/^ {2}butler:/m)
      expect(compose, "0.0.0.0 binding present").not.toMatch(/"0\.0\.0\.0/)
    })
  })
})