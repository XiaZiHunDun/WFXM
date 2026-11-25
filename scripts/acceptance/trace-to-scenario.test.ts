import { describe, expect, it } from "vitest"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import {
  buildScenarioDraft,
  parseTraceToScenarioArgs,
  renderDraftTest,
  slugify,
} from "./trace-to-scenario.js"

describe("parseTraceToScenarioArgs", () => {
  it("requires --turn", () => {
    expect(() => parseTraceToScenarioArgs([])).toThrow(/缺少 --turn/)
    expect(() => parseTraceToScenarioArgs(["--turn"])).toThrow(/缺少取值/)
  })

  it("accepts --turn / --out / --name", () => {
    const parsed = parseTraceToScenarioArgs([
      "--turn",
      "turn-172",
      "--out",
      "/tmp/drafts",
      "--name",
      "Wechat Failure",
    ])
    expect(parsed).toEqual({ turnId: "turn-172", outDir: "/tmp/drafts", slug: "wechat-failure" })
  })

  it("returns help without touching the database", () => {
    expect(parseTraceToScenarioArgs(["-h"])).toEqual({ help: true })
    expect(parseTraceToScenarioArgs(["--help"])).toEqual({ help: true })
  })

  it("rejects unknown flags", () => {
    expect(() => parseTraceToScenarioArgs(["--turn", "t", "--nope"])).toThrow(/未知参数/)
  })
})

describe("buildScenarioDraft", () => {
  it("projects the observed outcome from real trace shapes", () => {
    const events = [
      createTraceEvent({
        kind: "run",
        name: "start",
        status: "ok",
        turnId: "turn-9",
        conversationId: "c-1",
        runId: "run-1",
        nowMs: 1_000,
      }),
      createTraceEvent({
        kind: "step",
        name: "tool_write_file",
        status: "ok",
        turnId: "turn-9",
        detail: { tool: "write_file" },
        nowMs: 1_100,
      }),
      createTraceEvent({
        kind: "run",
        name: "finish",
        status: "error",
        turnId: "turn-9",
        detail: { error: "boom" },
        nowMs: 1_200,
      }),
    ]
    const draft = buildScenarioDraft(events, {
      turnId: "turn-9",
      generatedAt: "2026-11-25T00:00:00Z",
    })
    expect(draft.turnId).toBe("turn-9")
    expect(draft.conversationId).toBe("c-1")
    expect(draft.runId).toBe("run-1")
    expect(draft.observed.runStatus).toBe("failed")
    expect(draft.observed.toolCalls).toEqual(["write_file"])
    expect(draft.events).toHaveLength(3)
    expect(draft.note).toContain("草稿")
  })

  it("handles a turn with no terminal event", () => {
    const draft = buildScenarioDraft(
      [createTraceEvent({ kind: "step", name: "llm_call", status: "ok", nowMs: 1 })],
      { turnId: "turn-empty", generatedAt: "2026-11-25T00:00:00Z" },
    )
    expect(draft.observed.runStatus).toBeNull()
    expect(draft.observed.toolCalls).toEqual([])
  })
})

describe("renderDraftTest", () => {
  it("is skipped by default so drafts never break CI", () => {
    const draft = buildScenarioDraft([], { turnId: "turn-3", generatedAt: "2026-11-25T00:00:00Z" })
    const code = renderDraftTest(draft)
    expect(code).toContain('describe.skip("[draft] turn-3"')
    expect(code).toContain("TODO")
  })
})

describe("slugify", () => {
  it("keeps it filesystem-safe", () => {
    expect(slugify("Turn 172 / 微信")).toBe("turn-172")
    expect(slugify("///")).toBe("turn")
  })
})
