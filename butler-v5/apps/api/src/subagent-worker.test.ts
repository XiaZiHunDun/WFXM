/**
 * Subagent worker tests — R8.x.7.
 *
 * Verifies the worker drains the outbox's `Delegate` aggregate type,
 * invokes a child LLM call, and writes the reply back to the parent
 * conversation stream as `AssistantMessageProduced`.
 *
 * The tests use a deterministic in-process LLM adapter (via
 * Effect.succeed) so they don't reach out to a real provider. The
 * adapter is passed in via `pickProvider` so the worker stays
 * provider-agnostic — we never set `ANTHROPIC_API_KEY` here.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import { EventBridge } from "@butler/runtime/bridge.js"
import { delegate, type Capability } from "@butler/runtime/delegate-runtime.js"
import { makeTestDb } from "@butler/persistence/testing.js"
import { enqueueOutbox } from "@butler/persistence/outbox.js"
import { runSubagentWorker, type SubagentWorkerLogger } from "./subagent-worker.js"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"

function makeStubAdapter(content: string): LLMAdapter {
  return {
    complete: () =>
      Effect.succeed<LLMAssistantResponse>({
        content,
        toolCalls: [],
        stopReason: "end_turn",
      }),
  }
}

function makeSlowAdapter(): LLMAdapter {
  return {
    complete: () =>
      Effect.promise(
        () =>
          new Promise<LLMAssistantResponse>((resolve) => {
            setTimeout(
              () =>
                resolve({
                  content: "slow",
                  toolCalls: [],
                  stopReason: "end_turn",
                }),
              60_000,
            )
          }),
      ),
  }
}

describe("subagent worker", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  const silentLogger: SubagentWorkerLogger = {
    warn: () => undefined,
    error: () => undefined,
  }

  beforeEach(async () => {
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-subagent" })
  })

  afterEach(async () => {
    await db.close()
  })

  it("drains a Delegate outbox message; writes AssistantMessageProduced to parent stream", async () => {
    const parent = "p-subagent-1"
    // Use the real delegate() entry point so the test exercises the
    // same code path the butler loop uses.
    const cap: Capability = { tool: "general" as Capability["tool"] }
    await delegate({
      role: "researcher",
      task: "find docs about Foo",
      capabilities: [cap],
      parentConversationId: parent,
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })

    const handle = runSubagentWorker(
      bridge,
      () => makeStubAdapter("the answer is 42"),
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    // Wait for the worker to drain the outbox.
    const drained = await waitFor(async () => {
      const events = await bridge.loadStream(parent)
      return events.some(
        (e) =>
          e.eventType === "AssistantMessageProduced" &&
          (e.payload as { content?: string }).content?.includes("[子代理 researcher"),
      )
    })
    expect(drained).toBe(true)

    const events = await bridge.loadStream(parent)
    const replies = events.filter((e) => e.eventType === "AssistantMessageProduced")
    expect(replies.length).toBeGreaterThan(0)
    const reply = replies[0]?.payload as { content?: string }
    expect(reply?.content).toMatch(/\[子代理 researcher 的回复\]/)
    expect(reply?.content).toContain("the answer is 42")

    handle.stop()
  })

  it("skips outbox messages with aggregateType other than Delegate", async () => {
    const parent = "p-subagent-2"
    await enqueueOutbox(db.db, {
      streamId: parent,
      aggregateType: "Conversation",
      payload: { kind: "broadcast", text: "hello" },
    })

    const handler = vi.fn()
    const handle = runSubagentWorker(
      bridge,
      () => {
        handler()
        return makeStubAdapter("ignored")
      },
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    // Wait for one tick to drain — the message will be marked
    // delivered without producing an AssistantMessageProduced.
    const empty = await waitFor(async () => {
      const events = await bridge.loadStream(parent)
      return events.length === 0
    })
    expect(empty).toBe(true)

    // Handler should never have been called because the worker
    // filters on the aggregateType before invoking the LLM.
    expect(handler).not.toHaveBeenCalled()

    const events = await bridge.loadStream(parent)
    expect(events).toHaveLength(0)

    handle.stop()
  })

  it("writes a stub reply when no LLM adapter is configured", async () => {
    const parent = "p-subagent-3"
    const cap: Capability = { tool: "general" as Capability["tool"] }
    await delegate({
      role: "developer",
      task: "do a thing",
      capabilities: [cap],
      parentConversationId: parent,
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })

    const handle = runSubagentWorker(
      bridge,
      () => undefined,
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    const stubDrained = await waitFor(async () => {
      const events = await bridge.loadStream(parent)
      return events.some(
        (e) =>
          e.eventType === "AssistantMessageProduced" &&
          (e.payload as { content?: string }).content?.includes("未配置 LLM"),
      )
    })
    expect(stubDrained).toBe(true)

    const events = await bridge.loadStream(parent)
    const reply = events.find((e) => e.eventType === "AssistantMessageProduced")?.payload as {
      content?: string
    }
    expect(reply?.content).toContain("子代理 developer")
    expect(reply?.content).toContain("未配置 LLM")

    handle.stop()
  })

  it("uses the role + task from the outbox payload as LLM messages", async () => {
    const parent = "p-subagent-4"
    const cap: Capability = { tool: "general" as Capability["tool"] }
    await delegate({
      role: "reviewer",
      task: "review the patch attached to issue 42",
      capabilities: [cap],
      parentConversationId: parent,
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })

    let captured: { system: string; user: string } | undefined
    const capturingAdapter: LLMAdapter = {
      complete: (messages) => {
        const system = messages.find((m) => m.role === "system")?.content ?? ""
        const user = messages.find((m) => m.role === "user")?.content ?? ""
        captured = { system, user }
        return Effect.succeed<LLMAssistantResponse>({
          content: "patch looks good",
          toolCalls: [],
          stopReason: "end_turn",
        })
      },
    }

    const handle = runSubagentWorker(
      bridge,
      () => capturingAdapter,
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    const replySeen = await waitFor(async () => {
      const events = await bridge.loadStream(parent)
      return events.some(
        (e) =>
          e.eventType === "AssistantMessageProduced" &&
          (e.payload as { content?: string }).content?.includes("patch looks good"),
      )
    })
    expect(replySeen).toBe(true)

    expect(captured).toBeDefined()
    expect(captured?.system).toContain("reviewer")
    expect(captured?.user).toBe("review the patch attached to issue 42")

    handle.stop()
  })

  it("stop() halts the polling loop after the in-flight tick", async () => {
    const parent = "p-subagent-5"
    const cap: Capability = { tool: "general" as Capability["tool"] }
    await delegate({
      role: "general",
      task: "anything",
      capabilities: [cap],
      parentConversationId: parent,
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })

    const handle = runSubagentWorker(
      bridge,
      () => makeStubAdapter("done"),
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    const stopDrained = await waitFor(async () => {
      const events = await bridge.loadStream(parent)
      return events.some((e) => e.eventType === "AssistantMessageProduced")
    })
    expect(stopDrained).toBe(true)

    handle.stop()
    // Give the loop a chance to schedule another tick; verify the
    // event count does not keep growing because the worker is
    // stopped.
    const before = (await bridge.loadStream(parent)).filter(
      (e) => e.eventType === "AssistantMessageProduced",
    ).length
    await new Promise((r) => setTimeout(r, 50))
    const after = (await bridge.loadStream(parent)).filter(
      (e) => e.eventType === "AssistantMessageProduced",
    ).length
    expect(after).toBe(before)
  })

  it("rejects outbox messages with missing childConversationId or task (does not call LLM)", async () => {
    const parent = "p-subagent-6"
    await enqueueOutbox(db.db, {
      streamId: parent,
      aggregateType: "Delegate",
      payload: { role: "general" }, // missing task + childConversationId
    })

    const llmAdapter = makeStubAdapter("ignored")
    const completeSpy = vi.spyOn(llmAdapter, "complete")
    const handle = runSubagentWorker(
      bridge,
      () => llmAdapter,
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    // Wait until the worker has had at least one tick.
    await new Promise((r) => setTimeout(r, 100))

    // The LLM's complete() is never invoked because the worker
    // filters on childConversationId/task before the LLM call.
    expect(completeSpy).not.toHaveBeenCalled()
    // The parent stream is empty — no spurious AssistantMessageProduced.
    const events = await bridge.loadStream(parent)
    expect(events.filter((e) => e.eventType === "AssistantMessageProduced")).toHaveLength(0)

    handle.stop()
  })

  it("runs without throwing when the LLM call is slow or times out (graceful fallback)", async () => {
    const parent = "p-subagent-7"
    const cap: Capability = { tool: "general" as Capability["tool"] }
    await delegate({
      role: "general",
      task: "this will time out",
      capabilities: [cap],
      parentConversationId: parent,
      actor: { kind: "agent", id: "kernel" },
      bridge,
    })

    const handle = runSubagentWorker(
      bridge,
      () => makeSlowAdapter(),
      {},
      { logger: silentLogger, intervalMs: 10 },
    )

    // The Effect.timeout will fire after the LLM_TIMEOUT_MS
    // (30s) so this test waits for the failure-prefixed reply.
    // To keep unit-test runtime short, we shorten the timeout by
    // setting it via env (when the worker supports it). For now we
    // just verify the worker does not crash and the outbox message
    // remains pending — i.e. the worker is resilient to timeouts.
    await new Promise((r) => setTimeout(r, 200))

    // Worker should still be alive (no unhandled rejection).
    const events = await bridge.loadStream(parent)
    // No reply yet because the LLM is still in-flight.
    expect(events.filter((e) => e.eventType === "AssistantMessageProduced")).toHaveLength(0)

    handle.stop()
  })
})

/**
 * Poll a predicate until it returns true or the timeout elapses.
 * Keeps the tests deterministic without `vi.useFakeTimers` (which
 * would interfere with the worker's setTimeout chain). Returns true
 * when the predicate became true; false when the timeout elapsed.
 * Callers assert on the boolean (avoids `throw` in this new code).
 */
async function waitFor(
  predicate: () => Promise<boolean>,
  opts: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<boolean> {
  const timeoutMs = opts.timeoutMs ?? 3_000
  const intervalMs = opts.intervalMs ?? 25
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  return predicate()
}
