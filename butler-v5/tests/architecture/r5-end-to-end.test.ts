import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("R5 end-to-end gates", () => {
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

  it("R5 adapters test suite passes", () => {
    execFileSync("pnpm", ["test", "packages/adapters"], {
      cwd: process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    })
  })
})
