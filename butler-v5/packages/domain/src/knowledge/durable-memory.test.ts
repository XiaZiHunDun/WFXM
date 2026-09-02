import { describe, expect, it } from "vitest"
import {
  confirmDurableMemory,
  createDurableMemoryRecord,
  formatDurableMemoryPrefix,
  isDurableMemoryActive,
  matchDurableMemoryQuery,
  rejectDurableMemory,
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
    expect(confirmed.promotedBy).toBe("owner")
    expect(confirmed.promotedAt).toBeNull()
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

  it("rejected memory is inactive and excluded from recall", () => {
    const made = createDurableMemoryRecord({
      subject: "owner",
      content: "过时偏好",
      sourceKind: "owner",
      nowMs: 10,
    })
    expect(made.ok).toBe(true)
    if (!made.ok) return
    const rejected = rejectDurableMemory(made.value, 20)
    expect(rejected.status).toBe("rejected")
    expect(rejected.confirmedAt).toBeNull()
    expect(isDurableMemoryActive(rejected, 30)).toBe(false)
    expect(
      selectDurableMemoriesForWorkingSet({ records: [rejected], nowMs: 30 }).length,
    ).toBe(0)
  })

  it("expired confirmed memory is excluded despite matching query", () => {
    const made = createDurableMemoryRecord({
      id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
      subject: "owner",
      content: "临时口令 abc",
      sourceKind: "message",
      provenance: { messageId: "m9" },
      nowMs: 100,
      expiresAt: 200,
    })
    expect(made.ok).toBe(true)
    if (!made.ok) return
    const confirmed = confirmDurableMemory(made.value, 150)
    const selected = selectDurableMemoriesForWorkingSet({
      records: [confirmed],
      nowMs: 250,
      query: "口令",
    })
    expect(selected).toHaveLength(0)
  })

  it("substring match is case-insensitive and also scans the provenance note", () => {
    const made = createDurableMemoryRecord({
      id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      subject: "owner",
      content: "上班时间为 09:00",
      sourceKind: "message",
      provenance: { messageId: "m7", note: "trading Brent" },
      nowMs: 1,
    })
    expect(made.ok).toBe(true)
    if (!made.ok) return
    expect(matchDurableMemoryQuery(made.value, "Brent")).toBe(true)
    expect(matchDurableMemoryQuery(made.value, "brent")).toBe(true)
    expect(matchDurableMemoryQuery(made.value, "上班时间")).toBe(true)
    expect(matchDurableMemoryQuery(made.value, "")).toBe(true)
  })

  it("selects newest-first and clamps to limit", () => {
    const mk = (id: string, t: number) =>
      createDurableMemoryRecord({
        id,
        subject: "owner",
        content: `c${t}`,
        sourceKind: "owner",
        nowMs: t,
      })
    expect(mk("e", 1).ok && mk("f", 2).ok && mk("g", 3).ok).toBe(true)
    if (!mk("e", 1).ok || !mk("f", 2).ok || !mk("g", 3).ok) return
    const records = [mk("e", 1).value, mk("f", 2).value, mk("g", 3).value]
    const selected = selectDurableMemoriesForWorkingSet({
      records,
      nowMs: 99,
      limit: 2,
    })
    expect(selected.map((r) => r.id)).toEqual(["g", "f"])
    expect(selected).toHaveLength(2)
  })
})
