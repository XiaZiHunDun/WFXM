import { describe, expect, it } from "vitest"
import { runShadow } from "./shadow-runner.js"
import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

describe("Shadow runner", () => {
  it("returns ok with empty decisions when v4 root has no records", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "shadow-"))
    try {
      const r = await runShadow({ v4Root: tmp })
      expect(r.ok).toBe(true)
      if (r.ok) {
        expect(r.decisions.length).toBe(0)
        expect(r.mismatches).toBe(0)
      }
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  it("returns ok:false when v4Root does not exist", async () => {
    const r = await runShadow({ v4Root: "/nonexistent/path/that/cannot/exist" })
    expect(r.ok).toBe(false)
  })

  it("reports mismatches as a counter without throwing", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "shadow-"))
    try {
      const r = await runShadow({ v4Root: tmp })
      expect(r.ok).toBe(true)
      if (r.ok) expect(r.mismatches).toBe(0)
    } finally {
      rmSync(tmp, { recursive: true, force: true })
    }
  })
})
