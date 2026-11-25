import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createTraceEvent } from "@butler/domain/observability/local-trace.js"
import { createTraceStore } from "@butler/persistence"
import { makeTestDb, type TestDb } from "@butler/persistence/testing.js"
import { parseTraceExportArgs, writeTraceJsonl } from "./trace-export.js"

describe("parseTraceExportArgs", () => {
  it("defaults to limit 1000 and no filters", () => {
    expect(parseTraceExportArgs([])).toEqual({ filter: { limit: 1000 } })
  })

  it("parses every supported flag", () => {
    const parsed = parseTraceExportArgs([
      "--since",
      "2026-11-20",
      "--until",
      "2026-11-21",
      "--kind",
      "step",
      "--turn",
      "turn-172",
      "--conversation",
      "c-wechat-owner",
      "--limit",
      "5",
      "--out",
      "traces.jsonl",
    ])
    expect(parsed).toEqual({
      filter: {
        limit: 5,
        sinceMs: Date.parse("2026-11-20T00:00:00.000+08:00"),
        untilMs: Date.parse("2026-11-21T23:59:59.999+08:00"),
        kind: "step",
        turnId: "turn-172",
        conversationId: "c-wechat-owner",
      },
      out: "traces.jsonl",
    })
  })

  it("accepts full ISO timestamps", () => {
    const parsed = parseTraceExportArgs(["--since", "2026-11-20T10:00:00+08:00"])
    expect(parsed).toEqual({
      filter: { limit: 1000, sinceMs: Date.parse("2026-11-20T10:00:00+08:00") },
    })
  })

  it("rejects bad input", () => {
    expect(() => parseTraceExportArgs(["--kind", "nope"])).toThrow(/未知 kind/)
    expect(() => parseTraceExportArgs(["--limit", "0"])).toThrow(/--limit/)
    expect(() => parseTraceExportArgs(["--since"])).toThrow(/缺少取值/)
    expect(() => parseTraceExportArgs(["--since", "2026-11-21", "--until", "2026-11-20"])).toThrow(
      /--since 不能晚于 --until/,
    )
    expect(() => parseTraceExportArgs(["--bogus"])).toThrow(/未知参数/)
  })

  it("returns help for -h/--help", () => {
    expect(parseTraceExportArgs(["--help"])).toEqual({ help: true })
  })
})

describe("writeTraceJsonl", () => {
  let db: TestDb

  beforeEach(async () => {
    db = await makeTestDb()
  })

  afterEach(async () => {
    await db.close()
  })

  it("writes one JSON object per row with the persisted fields", async () => {
    const store = createTraceStore(db.db)
    await store.append([
      createTraceEvent({
        kind: "run",
        name: "failure",
        status: "error",
        turnId: "turn-1720000000",
        conversationId: "c-wechat-owner",
        runId: "run-1",
        detail: { code: "E-LLM-01" },
        nowMs: 1000,
      }),
      createTraceEvent({ kind: "step", name: "llm_call", runId: "run-1", nowMs: 2000 }),
    ])

    const lines: string[] = []
    const count = await writeTraceJsonl(store, { limit: 10 }, (chunk) => {
      lines.push(chunk)
    })

    expect(count).toBe(2)
    expect(lines).toHaveLength(2)
    const first = JSON.parse(lines[0] ?? "{}") as Record<string, unknown>
    expect(first["kind"]).toBe("run")
    expect(first["name"]).toBe("failure")
    expect(first["status"]).toBe("error")
    expect(first["turnId"]).toBe("turn-1720000000")
    expect(first["conversationId"]).toBe("c-wechat-owner")
    expect(first["detail"]).toEqual({ code: "E-LLM-01" })
    expect(first["createdAt"]).toBe(1000)
  })

  it("honours since/until and kind filters", async () => {
    const store = createTraceStore(db.db)
    await store.append([
      createTraceEvent({ kind: "run", name: "a", nowMs: 1000 }),
      createTraceEvent({ kind: "step", name: "b", nowMs: 2000 }),
      createTraceEvent({ kind: "step", name: "c", nowMs: 3000 }),
    ])

    const lines: string[] = []
    const count = await writeTraceJsonl(
      store,
      { kind: "step", sinceMs: 1500, untilMs: 2500, limit: 10 },
      (chunk) => lines.push(chunk),
    )
    expect(count).toBe(1)
    expect((JSON.parse(lines[0] ?? "{}") as Record<string, unknown>)["name"]).toBe("b")
  })
})
