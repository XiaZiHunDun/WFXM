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
    const tracer = createLocalTracer({ BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_MAX_EVENTS: "10" })
    tracer.record({ kind: "run", name: "a", nowMs: 1 })
    tracer.record({ kind: "run", name: "b", nowMs: 2 })
    expect(tracer.config.maxEvents).toBe(10)
    expect(tracer.size()).toBe(2)
    tracer.clear()
    expect(tracer.size()).toBe(0)
    expect(tracer.list()).toEqual([])
  })

  it("list without filter returns newest events capped by filter limit", () => {
    const tracer = createLocalTracer({ BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_MAX_EVENTS: "100" })
    for (let i = 0; i < 5; i++) tracer.record({ kind: "run", name: `e${i}`, nowMs: i })
    expect(tracer.list().map((e) => e.name)).toEqual(["e0", "e1", "e2", "e3", "e4"])
    expect(tracer.list({ limit: 2 }).map((e) => e.name)).toEqual(["e3", "e4"])
  })

  it("redacts secret strings recorded in name/capability", () => {
    const tracer = createLocalTracer({ BUTLER_V5_TRACE: "1", BUTLER_V5_TRACE_REDACT: "1" })
    const ev = tracer.record({
      kind: "capability",
      name: "Bearer abc.def.ghi",
      runId: "r1",
      nowMs: 1,
    })
    expect(ev?.name).toContain("***")
    expect(ev?.name).not.toContain("abc.def.ghi")
  })

  it("filters by turnId", () => {
    const tracer = createLocalTracer({ BUTLER_V5_TRACE: "1" })
    tracer.record({ kind: "run", name: "a", turnId: "turn-1", nowMs: 1 })
    tracer.record({ kind: "run", name: "b", turnId: "turn-2", nowMs: 2 })
    expect(tracer.list({ turnId: "turn-1" }).map((e) => e.name)).toEqual(["a"])
  })
})

describe("localTracer sink", () => {
  it("batches queued events into the sink", async () => {
    const batches: string[][] = []
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1" },
      {
        batchSize: 2,
        flushIntervalMs: 60_000,
        sink: {
          append: async (events) => {
            batches.push(events.map((e) => e.name))
          },
        },
      },
    )
    tracer.record({ kind: "run", name: "a", nowMs: 1 })
    tracer.record({ kind: "run", name: "b", nowMs: 2 })
    await tracer.flush()
    expect(batches.flat()).toEqual(["a", "b"])
    expect(tracer.stats()).toEqual({ written: 2, dropped: 0 })
    expect(tracer.pending()).toBe(0)
    await tracer.close()
  })

  it("flush writes remaining events below the batch threshold", async () => {
    let written = 0
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1" },
      {
        batchSize: 50,
        flushIntervalMs: 60_000,
        sink: {
          append: async (events) => {
            written += events.length
          },
        },
      },
    )
    tracer.record({ kind: "run", name: "only", nowMs: 1 })
    expect(tracer.pending()).toBe(1)
    await tracer.flush()
    expect(written).toBe(1)
    expect(tracer.pending()).toBe(0)
    await tracer.close()
  })

  it("never throws when the sink fails; counts dropped events", async () => {
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1" },
      {
        batchSize: 1,
        flushIntervalMs: 60_000,
        sink: {
          append: async () => {
            throw new Error("db down")
          },
        },
      },
    )
    tracer.record({ kind: "run", name: "a", nowMs: 1 })
    await tracer.flush()
    expect(tracer.stats().dropped).toBe(1)
    expect(tracer.stats().written).toBe(0)
    expect(tracer.pending()).toBe(0)
    await tracer.close()
  })

  it("does not write to the sink when tracing is disabled", async () => {
    let called = 0
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "0" },
      {
        batchSize: 1,
        flushIntervalMs: 60_000,
        sink: {
          append: async () => {
            called += 1
          },
        },
      },
    )
    tracer.record({ kind: "run", name: "a" })
    await tracer.flush()
    expect(called).toBe(0)
    expect(tracer.stats()).toEqual({ written: 0, dropped: 0 })
    await tracer.close()
  })

  it("close flushes pending events", async () => {
    let written = 0
    const tracer = createLocalTracer(
      { BUTLER_V5_TRACE: "1" },
      {
        batchSize: 50,
        flushIntervalMs: 60_000,
        sink: {
          append: async (events) => {
            written += events.length
          },
        },
      },
    )
    tracer.record({ kind: "run", name: "a", nowMs: 1 })
    await tracer.close()
    expect(written).toBe(1)
    expect(tracer.pending()).toBe(0)
  })
})
