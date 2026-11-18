import { existsSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createButlerMemoryFromEnv } from "./butler-memory-bootstrap.js"

let root: string
let file: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "butler-memory-"))
  file = join(root, "nested", "memory.json")
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

describe("createButlerMemoryFromEnv", () => {
  it("stays disabled without a path and owner", async () => {
    expect(await createButlerMemoryFromEnv({})).toBeNull()
    expect(await createButlerMemoryFromEnv({ BUTLER_V5_MEMORY_PATH: file })).toBeNull()
    expect(
      await createButlerMemoryFromEnv({
        BUTLER_V5_MEMORY_PATH: file,
        BUTLER_V5_OWNER_ID: "  ",
      }),
    ).toBeNull()
    expect(existsSync(file)).toBe(false)
  })

  it("persists user memory across restarts", async () => {
    const env = { BUTLER_V5_MEMORY_PATH: file, BUTLER_V5_OWNER_ID: "user-1" }
    const first = await createButlerMemoryFromEnv(env)
    expect(first?.ownerId).toBe("user-1")

    await first?.ports.butler.recordSessionSummary({
      userId: "user-1",
      sessionId: "s1",
      summary: "用户偏好中文回复，部署前要先跑测试。",
      profile: { preferences: ["中文回复", "部署前跑测试"] },
      occurredAt: "2026-11-17T10:00:00.000Z",
    })
    expect(existsSync(file)).toBe(true)
    const recalled = await first?.ports.butler.recallUserMemory("中文")
    expect(recalled && recalled.length > 0).toBe(true)

    const second = await createButlerMemoryFromEnv(env)
    const afterRestart = await second?.ports.butler.recallUserMemory("部署")
    expect(afterRestart && afterRestart.length > 0).toBe(true)
  })
})
