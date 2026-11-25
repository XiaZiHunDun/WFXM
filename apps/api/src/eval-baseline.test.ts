import { mkdtemp, rm, utimes, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { readEvalBaseline } from "./eval-baseline.js"

const DAY_MS = 24 * 60 * 60 * 1000
const NOW = Date.UTC(2026, 10, 25, 1, 0, 0)

describe("readEvalBaseline", () => {
  let dir: string

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), "eval-baseline-"))
  })

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  function env(extra: Record<string, string> = {}): NodeJS.ProcessEnv {
    return {
      BUTLER_V5_WORKSPACE_ROOT: dir,
      BUTLER_V5_EVAL_RECORDINGS_DIR: dir,
      ...extra,
    } as NodeJS.ProcessEnv
  }

  it("reports a missing directory as stale without throwing", async () => {
    const status = await readEvalBaseline(
      { BUTLER_V5_EVAL_RECORDINGS_DIR: join(dir, "nope") } as NodeJS.ProcessEnv,
      NOW,
    )
    expect(status.count).toBe(0)
    expect(status.age_days).toBeNull()
    expect(status.stale).toBe(true)
  })

  it("reports a fresh recording as not stale", async () => {
    const file = join(dir, "run.json")
    await writeFile(file, "{}")
    const stamp = new Date(NOW - 2 * DAY_MS)
    await utimes(file, stamp, stamp)

    const status = await readEvalBaseline(env(), NOW)
    expect(status.count).toBe(1)
    expect(status.age_days).toBe(2)
    expect(status.stale).toBe(false)
    expect(status.max_age_days).toBe(30)
    expect(status.latest_at).toBe(stamp.toISOString())
  })

  it("flags an old recording and ignores non-json files", async () => {
    const oldFile = join(dir, "old.json")
    await writeFile(oldFile, "{}")
    const stamp = new Date(NOW - 45 * DAY_MS)
    await utimes(oldFile, stamp, stamp)
    await writeFile(join(dir, "notes.txt"), "ignore me")

    const status = await readEvalBaseline(env({ BUTLER_V5_EVAL_BASELINE_MAX_AGE_DAYS: "7" }), NOW)
    expect(status.count).toBe(1)
    expect(status.age_days).toBe(45)
    expect(status.max_age_days).toBe(7)
    expect(status.stale).toBe(true)
  })
})
