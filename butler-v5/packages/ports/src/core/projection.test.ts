import { describe, expect, it } from "vitest"
import { memoryProjection } from "./projection.js"
import type { ProjectionPort } from "./projection.js"

describe("ProjectionPort (memory impl)", () => {
  it("apply resolves without throwing on memory impl", async () => {
    const p: ProjectionPort = memoryProjection()
    await expect(p.apply("s1", "user_view")).resolves.toBeUndefined()
  })

  it("rebuild resolves without throwing on memory impl", async () => {
    const p: ProjectionPort = memoryProjection()
    await expect(p.rebuild("s1", "user_view")).resolves.toBeUndefined()
  })

  it("register accepts and stores handler under name; can be replaced", async () => {
    const p: ProjectionPort = memoryProjection()
    let called = 0
    await p.register("counter", (..._args) => {
      called++
    })
    // 内存实现不自动调用 handlers，但 register 不抛错且可覆盖
    await expect(p.register("counter", () => {})).resolves.toBeUndefined()
    expect(called).toBe(0)
  })
})
