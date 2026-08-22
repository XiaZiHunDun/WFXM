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
})
