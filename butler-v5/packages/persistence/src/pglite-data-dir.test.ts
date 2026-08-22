import { describe, expect, it } from "vitest"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { resolvePgliteDataDir } from "./pglite-data-dir.js"

describe("resolvePgliteDataDir", () => {
  it("uses in-memory for vitest", () => {
    expect(resolvePgliteDataDir({ NODE_ENV: "test", VITEST: "true" })).toBeUndefined()
  })

  it("defaults to ~/.butler/v5-data when unset outside tests", () => {
    const dir = resolvePgliteDataDir({ NODE_ENV: "development" })
    expect(dir).toMatch(/\.butler[\\/]v5-data$/)
  })

  it("honors memory override", () => {
    expect(resolvePgliteDataDir({ BUTLER_V5_PGLITE_DATA_DIR: "memory" })).toBeUndefined()
  })

  it("expands explicit paths", () => {
    const tmp = mkdtempSync(join(tmpdir(), "pglite-dir-test-"))
    try {
      expect(resolvePgliteDataDir({ BUTLER_V5_PGLITE_DATA_DIR: tmp })).toBe(tmp)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })
})
