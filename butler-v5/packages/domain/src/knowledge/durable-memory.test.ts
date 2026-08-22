import { describe, expect, it } from "vitest"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  formatDurableMemoryPrefix,
  isDurableMemoryActive,
  selectDurableMemoriesForWorkingSet,
} from "./durable-memory.js"

describe("durable memory", () => {
  it("creates owner memory as confirmed by default", () => {
    const created = createDurableMemoryRecord({
      subject: "owner",
      content: "喜欢简短回复",
      sourceKind: "owner",
      nowMs: 1000,
    })
    expect(created.ok).toBe(true)
    if (!created.ok) return
    expect(created.value.status).toBe("confirmed")
    expect(isDurableMemoryActive(created.value, 2000)).toBe(true)
  })

  it("requires messageId for message provenance and defaults to candidate", () => {
    expect(
      createDurableMemoryRecord({
        subject: "owner",
        content: "事实",
        sourceKind: "message",
        nowMs: 1,
      }).ok,
    ).toBe(false)

    const created = createDurableMemoryRecord({
      subject: "owner",
      content: "事实",
      sourceKind: "message",
      provenance: { messageId: "m1", conversationId: "c1" },
      nowMs: 1,
    })
    expect(created.ok).toBe(true)
    if (!created.ok) return
    expect(created.value.status).toBe("candidate")
    expect(isDurableMemoryActive(created.value, 2)).toBe(false)
  })

  it("selects active memories and formats prefix", () => {
    const a = createDurableMemoryRecord({
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      subject: "owner",
      content: "时区 Asia/Shanghai",
      sourceKind: "owner",
      nowMs: 10,
    })
    const b = createDurableMemoryRecord({
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      subject: "owner",
      content: "候选",
      sourceKind: "message",
      provenance: { messageId: "m2" },
      nowMs: 20,
    })
    expect(a.ok && b.ok).toBe(true)
    if (!a.ok || !b.ok) return
    const confirmed = confirmDurableMemory(b.value, 30)
    const selected = selectDurableMemoriesForWorkingSet({
      records: [a.value, confirmed],
      nowMs: 40,
      query: "时区",
      limit: 5,
    })
    expect(selected).toHaveLength(1)
    expect(selected[0]?.content).toContain("时区")
    const prefix = formatDurableMemoryPrefix(selected)
    expect(prefix).toContain("Durable Memory")
    expect(prefix).toContain("时区")
  })
})
