import { describe, expect, it } from "vitest"
import {
  applyTraceRedaction,
  createTraceEvent,
  filterTraceEvents,
  formatOtelStdoutLine,
  parseTraceConfig,
  redactTraceText,
  redactTraceValue,
} from "./local-trace.js"

function expectDefined<T>(value: T | undefined): T {
  expect(value).toBeDefined()
  return value as T
}

describe("local trace", () => {
  it("parses config with local default on and otel off", () => {
    expect(parseTraceConfig({})).toMatchObject({
      enabled: true,
      redact: true,
      exporter: "off",
    })
    expect(parseTraceConfig({ BUTLER_V5_TRACE: "0" }).enabled).toBe(false)
    expect(parseTraceConfig({ BUTLER_V5_OTEL_EXPORTER: "stdout" }).exporter).toBe("stdout")
  })

  it("redacts secrets", () => {
    expect(redactTraceText("Bearer abc.def.ghi")).toContain("***")
    expect(redactTraceText("api_key=supersecret")).toContain("***")
    expect(redactTraceText("AKIAIOSFODNN7EXAMPLE")).toBe("***")
    expect(
      redactTraceText(
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
      ),
    ).toBe("***")
    const event = applyTraceRedaction(
      createTraceEvent({
        kind: "capability",
        name: "run",
        subject: "Bearer leaked-token-value",
        detail: { authorization: "secret-token", path: "/tmp/a" },
        nowMs: 1,
      }),
    )
    expect(event.detail["authorization"]).toBe("***")
    expect(event.detail["path"]).toBe("/tmp/a")
    expect(event.subject).toContain("***")
  })

  it("filters and formats otel stdout line", () => {
    const a = createTraceEvent({
      kind: "run",
      name: "inbound",
      runId: "11111111-1111-1111-1111-111111111111",
      conversationId: "c1",
      nowMs: 10,
    })
    const b = createTraceEvent({
      kind: "policy",
      name: "Ask",
      runId: a.runId,
      policyDecision: "Ask",
      nowMs: 11,
    })
    expect(filterTraceEvents([a, b], { kind: "policy" })).toHaveLength(1)
    const line = formatOtelStdoutLine(a)
    expect(line).toContain("resourceSpans")
    expect(line).toContain("butler.runId")
  })

  it("formats OTLP line with deterministic traceId/spanId/status/duration", () => {
    const ev = createTraceEvent({
      kind: "run",
      name: "finish",
      status: "ok",
      runId: "22222222-2222-2222-2222-222222222222",
      conversationId: "c1",
      capability: "read_file",
      policyDecision: "Allow",
      durationMs: 125,
      nowMs: 1000,
    })
    const line = JSON.parse(formatOtelStdoutLine(ev)) as {
      resourceSpans: {
        scopeSpans: { spans: {
          traceId: string
          spanId: string
          name: string
          kind: number
          startTimeUnixNano: string
          endTimeUnixNano: string
          status: { code: number }
          attributes: { key: string; value: { stringValue: string } }[]
        }[] }[]
      }[]
    }
    const span = expectDefined(line.resourceSpans[0]?.scopeSpans[0]?.spans[0])
    expect(span.traceId).toBe((ev.runId as string).replace(/-/g, "").padEnd(32, "0").slice(0, 32))
    expect(span.spanId).toHaveLength(16)
    expect(span.name).toBe("run:finish")
    expect(span.startTimeUnixNano).toBe(String(1000 * 1_000_000))
    expect(span.endTimeUnixNano).toBe(String(1125 * 1_000_000)) // start + durationMs
    expect(span.status.code).toBe(1) // ok
    expect(span.attributes).toContainEqual({
      key: "butler.capability",
      value: { stringValue: "read_file" },
    })

    const error = createTraceEvent({ kind: "grant", name: "deny", status: "error", nowMs: 1 })
    const waiting = createTraceEvent({ kind: "step", name: "wait", status: "waiting", nowMs: 1 })
    const errSpan = JSON.parse(formatOtelStdoutLine(error))
    const waitSpan = JSON.parse(formatOtelStdoutLine(waiting))
    expect(errSpan.resourceSpans[0].scopeSpans[0].spans[0].status.code).toBe(2)
    expect(waitSpan.resourceSpans[0].scopeSpans[0].spans[0].status.code).toBe(0)
  })

  it("redacts nested object keys and truncates arrays/depth", () => {
    const out = redactTraceValue({
      apiKey: "abc",
      nested: { secret: "s1", token: "t1", keep: "ok" },
      list: Array.from({ length: 30 }, (_, i) => i),
    })
    expect(out).toEqual({
      apiKey: "***",
      nested: { secret: "***", token: "***", keep: "ok" },
      list: Array.from({ length: 20 }, (_, i) => i),
    })
  })

  it("filters by runId/conversationId/kind and slices limit", () => {
    const base = (kind: "run" | "policy", name: string, runId: string, conv: string, t: number) =>
      createTraceEvent({ kind, name, runId, conversationId: conv, nowMs: t })
    const events = [
      base("run", "a", "r1", "c1", 1),
      base("run", "b", "r1", "c2", 2),
      base("policy", "c", "r2", "c2", 3),
    ]
    expect(filterTraceEvents(events, { runId: "r1" }).map((e) => e.name)).toEqual(["a", "b"])
    expect(filterTraceEvents(events, { conversationId: "c2" }).map((e) => e.name)).toEqual([
      "b",
      "c",
    ])
    expect(filterTraceEvents(events, { runId: "r1", limit: 1 }).map((e) => e.name)).toEqual(["b"])
    expect(filterTraceEvents(events, { limit: 0 })).toEqual([])
  })
})
