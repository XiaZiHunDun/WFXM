import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"
import { mkdtempSync, rmSync, existsSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

describe("final cutover script", () => {
  it("--dry-run produces a final-cutover manifest with all steps marked skipped", () => {
    const tmp = mkdtempSync(join(tmpdir(), "final-"))
    try {
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/run-final-cutover.mjs",
          "--v4-root",
          tmp,
          "--dry-run",
          "--out-dir",
          join(tmp, "out"),
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/dry-run final cutover/i)
      expect(existsSync(join(tmp, "out", "final-cutover-manifest.json"))).toBe(true)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("--live requires R7.1 prepare-manifest.json to exist", () => {
    const tmp = mkdtempSync(join(tmpdir(), "final-"))
    try {
      writeFileSync(
        join(tmp, "prepare-manifest.json"),
        JSON.stringify({ dryRun: false, live: true, eventsWritten: 0 }),
      )
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/run-final-cutover.mjs",
          "--v4-root",
          tmp,
          "--live",
          "--out-dir",
          join(tmp, "out"),
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/live final cutover/i)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("exits 1 when --v4-root is missing", () => {
    expect(() => {
      execFileSync("node", ["scripts/cutover/run-final-cutover.mjs"], {
        stdio: ["ignore", "pipe", "pipe"],
      })
    }).toThrow(/required|error|exit code 1/i)
  })
})
