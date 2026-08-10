import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"
import { mkdtempSync, rmSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

describe("cutover script", () => {
  it("--dry-run writes a manifest but no events", () => {
    const tmp = mkdtempSync(join(tmpdir(), "cutover-"))
    try {
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/run-cutover.mjs",
          "--v4-root",
          tmp,
          "--dry-run",
          "--out-dir",
          join(tmp, "out"),
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/dry-run cutover manifest/i)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("manifest is parseable as JSON when --write-manifest is set", () => {
    const tmp = mkdtempSync(join(tmpdir(), "cutover-"))
    try {
      execFileSync(
        "node",
        [
          "scripts/cutover/run-cutover.mjs",
          "--v4-root",
          tmp,
          "--dry-run",
          "--out-dir",
          join(tmp, "out"),
          "--write-manifest",
        ],
        { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      const manifest = JSON.parse(readFileSync(join(tmp, "out", "cutover-manifest.json"), "utf8"))
      expect(manifest.dryRun).toBe(true)
      expect(typeof manifest.eventsWritten).toBe("number")
      expect(manifest.steps.length).toBe(5)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("exits 1 when --v4-root is missing", () => {
    expect(() => {
      execFileSync("node", ["scripts/cutover/run-cutover.mjs"], {
        stdio: ["ignore", "pipe", "pipe"],
      })
    }).toThrow(/required|error|exit code 1/i)
  })
})
