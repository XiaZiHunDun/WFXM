import { describe, expect, it } from "vitest"
import { memorySnapshot } from "./snapshot.js"
import type { SnapshotPort } from "./snapshot.js"

/** Type narrowing helper avoiding `!` non-null assertions (project ESLint disallows them). */
function expectDefined<T>(value: T | null | undefined): T {
  expect(value).toBeDefined()
  return value as T
}

describe("SnapshotPort (memory impl)", () => {
  it("load returns null when nothing saved", async () => {
    const s: SnapshotPort = memorySnapshot()
    expect(await s.load("missing")).toBeNull()
  })

  it("save then load returns same payload", async () => {
    const s: SnapshotPort = memorySnapshot()
    await s.save("s1", 5, { state: "active" })
    const rec = expectDefined(await s.load("s1"))
    expect(rec.streamVersion).toBe(5)
    expect(rec.payload).toEqual({ state: "active" })
  })

  it("save overwrites earlier snapshot with new version", async () => {
    const s: SnapshotPort = memorySnapshot()
    await s.save("s1", 1, { v: 1 })
    await s.save("s1", 7, { v: 7 })
    const rec = expectDefined(await s.load("s1"))
    expect(rec.streamVersion).toBe(7)
    expect(rec.payload).toEqual({ v: 7 })
  })

  it("save/load scoped by streamId", async () => {
    const s: SnapshotPort = memorySnapshot()
    await s.save("s1", 1, { tag: "a" })
    await s.save("s2", 1, { tag: "b" })
    const recA = expectDefined(await s.load("s1"))
    const recB = expectDefined(await s.load("s2"))
    expect(recA.payload).toEqual({ tag: "a" })
    expect(recB.payload).toEqual({ tag: "b" })
  })
})
