import { describe, expect, it } from "vitest"
import {
  applyTraceRedaction,
  createTraceEvent,
  filterTraceEvents,
  formatOtelStdoutLine,
  parseTraceConfig,
  redactTraceText,
} from "./local-trace.js"

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
})
