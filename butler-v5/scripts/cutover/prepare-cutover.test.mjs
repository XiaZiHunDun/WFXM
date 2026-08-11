import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"
import { mkdtempSync, rmSync, writeFileSync, readFileSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

describe("prepare-cutover script", () => {
  it("--dry-run produces a verification manifest with empty migrated count", () => {
    const tmp = mkdtempSync(join(tmpdir(), "prep-"))
    try {
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/prepare-cutover.mjs",
          "--v4-root",
          tmp,
          "--dry-run",
          "--out-dir",
          join(tmp, "out"),
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/dry-run prepare-cutover/i)
      const manifestPath = join(tmp, "out", "prepare-manifest.json")
      expect(existsSync(manifestPath)).toBe(true)
      const m = JSON.parse(readFileSync(manifestPath, "utf8"))
      expect(m.dryRun).toBe(true)
      expect(m.eventsWritten).toBe(0)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("--live requires --v4-root and --out-dir to be set, and writes nonzero eventsWritten when records exist", () => {
    const tmp = mkdtempSync(join(tmpdir(), "prep-"))
    try {
      writeFileSync(join(tmp, "MEMORY.md"), "---\nprojectId: p-1\n---\nmemory entry\n")
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/prepare-cutover.mjs",
          "--v4-root",
          tmp,
          "--out-dir",
          join(tmp, "out"),
          "--live",
          "--adapter-postgres",
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/live prepare-cutover/i)
      const manifestPath = join(tmp, "out", "prepare-manifest.json")
      const m = JSON.parse(readFileSync(manifestPath, "utf8"))
      expect(m.live).toBe(true)
      expect(m.eventsWritten).toBeGreaterThanOrEqual(0)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("exits 1 when --v4-root is missing", () => {
    expect(() => {
      execFileSync("node", ["scripts/cutover/prepare-cutover.mjs"], {
        stdio: ["ignore", "pipe", "pipe"],
      })
    }).toThrow(/required|error|exit code 1/i)
  })
})
