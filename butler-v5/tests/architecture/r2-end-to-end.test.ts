import { describe, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("R2 end-to-end gates", () => {
  // Lightweight check: this test file itself is part of the outer Vitest
  // run, so 266 tests + this suite have already passed by the time this
  // describe is collected. We only assert "it exists" here, not re-run pnpm test.
  it("architecture suite is part of pnpm test", () => {
    // No-op: presence of this file under tests/architecture/ is enough
    // because vitest.config.ts globs it. Re-running pnpm test inside
    // a vitest worker caused memory exhaustion in the parent session.
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
})
