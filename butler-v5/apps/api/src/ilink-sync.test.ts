import { mkdtempSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { loadSyncBuf, saveSyncBuf } from "./ilink-sync.js"

describe("ilink sync buf persistence", () => {
  it("round-trips get_updates_buf", () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-v5-sync-"))
    const path = join(dir, "ilink-sync.json")
    expect(loadSyncBuf(path)).toBe("")
    saveSyncBuf(path, "cursor-9")
    expect(loadSyncBuf(path)).toBe("cursor-9")
    expect(JSON.parse(readFileSync(path, "utf8"))).toEqual({ get_updates_buf: "cursor-9" })
  })
})
