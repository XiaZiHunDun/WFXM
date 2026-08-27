import { describe, expect, it } from "vitest"
import { createLocalTracer } from "./local-tracer.js"

describe("localTracer", () => {
  it("records into a ring buffer and exports stdout when enabled", () => {
    const lines: string[] = []
    const tracer = createLocalTracer(
      {
        BUTLER_V5_TRACE: "1",
        BUTLER_V5_TRACE_MAX_EVENTS: "2",
        BUTLER_V5_OTEL_EXPORTER: "stdout",
      },
      { writeStdout: (line) => lines.push(line) },
    )
    tracer.record({ kind: "run", name: "a", runId: "r1", nowMs: 1 })
    tracer.record({ kind: "capability", name: "read_file", runId: "r1", nowMs: 2 })
    tracer.record({ kind: "policy", name: "Allow", runId: "r1", nowMs: 3 })
    expect(tracer.size()).toBe(2)
    expect(tracer.list({ runId: "r1" }).map((e) => e.name)).toEqual(["read_file", "Allow"])
    expect(lines.length).toBe(3)
    expect(lines[0]).toContain("resourceSpans")
  })

  it("no-ops when disabled", () => {
    const tracer = createLocalTracer({ BUTLER_V5_TRACE: "0" })
    expect(tracer.record({ kind: "run", name: "x" })).toBeNull()
    expect(tracer.size()).toBe(0)
  })

  it("clear empties the buffer and config is exposed", () => {
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_MAX_EVENTS: "10" },
    )
    tracer.record({ kind: "run", name: "a", nowMs: 1 })
    tracer.record({ kind: "run", name: "b", nowMs: 2 })
    expect(tracer.config.maxEvents).toBe(10)
    expect(tracer.size()).toBe(2)
    tracer.clear()
    expect(tracer.size()).toBe(0)
    expect(tracer.list()).toEqual([])
  })

  it("list without filter returns newest events capped by filter limit", () => {
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_MAX_EVENTS: "100" },
    )
    for (let i = 0; i < 5; i++) tracer.record({ kind: "run", name: `e${i}`, nowMs: i })
    expect(tracer.list().map((e) => e.name)).toEqual(["e0", "e1", "e2", "e3", "e4"])
    expect(tracer.list({ limit: 2 }).map((e) => e.name)).toEqual(["e3", "e4"])
  })

  it("redacts secret strings recorded in name/capability", () => {
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_REDACT: "1" },
    )
    const ev = tracer.record({
      kind: "capability",
      name: "Bearer abc.def.ghi",
      runId: "r1",
      nowMs: 1,
    })
    expect(ev?.name).toContain("***")
    expect(ev?.name).not.toContain("abc.def.ghi")
  })
})
