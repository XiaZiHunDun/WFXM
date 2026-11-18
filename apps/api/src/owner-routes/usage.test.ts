import { describe, expect, it, beforeEach } from "vitest"
import {
  getSharedLocalTracer,
  resetSharedLocalTracer,
} from "@butler/runtime/observability/local-tracer.js"
import { aggregateUsage, type UsageAggregate } from "./usage.js"

describe("aggregateUsage", () => {
  beforeEach(() => {
    resetSharedLocalTracer({ BUTLER_V5_TRACE: "1" })
  })

  it("aggregates llm_call events by conversationId (counts + tokens + cost)", () => {
    const tracer = getSharedLocalTracer()
    tracer.record({
      kind: "step",
      name: "llm_call",
      status: "ok",
      conversationId: "conv-1",
      runId: "r1",
      nowMs: 1,
      token: { inputTokens: 100, outputTokens: 50, totalTokens: 150 },
      costUsd: 0.001,
    })
    tracer.record({
      kind: "step",
      name: "llm_call",
      status: "ok",
      conversationId: "conv-2",
      runId: "r2",
      nowMs: 2,
      token: { inputTokens: 200, outputTokens: 80, totalTokens: 280 },
    })
    const agg: UsageAggregate = aggregateUsage(tracer.list())
    expect(agg.totals.llmCalls).toBe(2)
    expect(agg.totals.totalTokens).toBe(430)
    expect(agg.totals.costUsd).toBeCloseTo(0.001)
    expect(agg.conversations["conv-1"]?.llmCalls).toBe(1)
    expect(agg.conversations["conv-1"]?.inputTokens).toBe(100)
    expect(agg.conversations["conv-1"]?.outputTokens).toBe(50)
    expect(agg.conversations["conv-1"]?.totalTokens).toBe(150)
    expect(agg.conversations["conv-1"]?.costUsd).toBeCloseTo(0.001)
    expect(agg.conversations["conv-2"]?.llmCalls).toBe(1)
  })

  it("aggregates capability events by name + conversationId", () => {
    const tracer = getSharedLocalTracer()
    tracer.record({
      kind: "capability",
      name: "read_file",
      status: "ok",
      conversationId: "conv-1",
      runId: "r1",
      nowMs: 1,
    })
    tracer.record({
      kind: "capability",
      name: "read_file",
      status: "ok",
      conversationId: "conv-1",
      runId: "r1",
      nowMs: 2,
    })
    tracer.record({
      kind: "capability",
      name: "write_file",
      status: "ok",
      conversationId: "conv-1",
      runId: "r1",
      nowMs: 3,
    })
    const agg = aggregateUsage(tracer.list())
    expect(agg.conversations["conv-1"]?.capabilityCalls).toEqual({
      read_file: 2,
      write_file: 1,
    })
    expect(agg.totals.capabilityCalls).toBe(3)
  })

  it("events without conversationId bucket under _unscoped", () => {
    const tracer = getSharedLocalTracer()
    tracer.record({
      kind: "capability",
      name: "general",
      status: "ok",
      nowMs: 1, // no conversationId
    })
    const agg = aggregateUsage(tracer.list())
    expect(agg.conversations["_unscoped"]?.capabilityCalls).toEqual({ general: 1 })
  })

  it("non-llm_call step events ignored", () => {
    const tracer = getSharedLocalTracer()
    tracer.record({
      kind: "step",
      name: "tool_lookup", // not llm_call
      status: "ok",
      conversationId: "conv-1",
      nowMs: 1,
    })
    const agg = aggregateUsage(tracer.list())
    expect(agg.totals.llmCalls).toBe(0)
    expect(agg.conversations["conv-1"]?.llmCalls).toBe(0)
  })
})
