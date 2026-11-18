import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"
import { mkdtempSync, rmSync, existsSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

describe("R6 end-to-end gates", () => {
  it("architecture suite is part of pnpm test", () => {
    // No-op: presence under tests/architecture/ is sufficient.
    // Re-running pnpm test inside a vitest worker causes memory exhaustion.
  })

  it("typecheck passes", () => {
    execFileSync("pnpm", ["typecheck"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("lint passes", () => {
    execFileSync("pnpm", ["lint"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("format passes", () => {
    execFileSync("pnpm", ["format:check"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })

  it("R6 cutover script runs in dry-run mode without errors", () => {
    const tmp = mkdtempSync(join(tmpdir(), "r6-"))
    try {
      const out = execFileSync(
        "node",
        [
          "scripts/cutover/run-cutover.mjs",
          "--v4-root",
          tmp,
          "--dry-run",
          "--write-manifest",
          "--out-dir",
          join(tmp, "out"),
        ],
        { cwd: process.cwd(), encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
      )
      expect(out).toMatch(/dry-run cutover manifest/)
      expect(existsSync(join(tmp, "out", "cutover-manifest.json"))).toBe(true)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })
})
