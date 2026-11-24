import { describe, expect, it } from "vitest"
import { makeTestDb } from "@butler/persistence/testing.js"
import { createRuntimeStore } from "@butler/persistence/runtime-store.js"
import {
  devSessionAutoGrantEnabled,
  devSessionRunId,
  ensureDevSessionGrants,
  formatDevSessionEnabledReply,
  isDevSessionPhrase,
} from "./dev-session-grant.js"

describe("dev-session-grant", () => {
  it("detects dev session phrases", () => {
    expect(isDevSessionPhrase("开发模式")).toBe(true)
    expect(isDevSessionPhrase("/dev mode")).toBe(true)
    expect(isDevSessionPhrase("你好")).toBe(false)
  })

  it("auto-grant stays on unless explicitly disabled", () => {
    expect(devSessionAutoGrantEnabled({} as NodeJS.ProcessEnv)).toBe(true)
    expect(devSessionAutoGrantEnabled({ BUTLER_V5_DEV_SESSION_AUTO_GRANT: "" })).toBe(true)
    expect(devSessionAutoGrantEnabled({ BUTLER_V5_DEV_SESSION_AUTO_GRANT: "1" })).toBe(true)
    expect(devSessionAutoGrantEnabled({ BUTLER_V5_DEV_SESSION_AUTO_GRANT: "0" })).toBe(false)
    expect(devSessionAutoGrantEnabled({ BUTLER_V5_DEV_SESSION_AUTO_GRANT: "false" })).toBe(false)
  })

  it("creates scoped_grants-backed session grants", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db.db)
    const isolatedEnv = { BUTLER_OWNER_WECHAT_ID: "" } as NodeJS.ProcessEnv
    try {
      const subject = "owner-wechat"
      const session = await ensureDevSessionGrants({
        store,
        subject,
        env: isolatedEnv,
      })
      expect(session.maxUses).toBeGreaterThan(0)

      const grant = await store.findActiveGrant({
        runId: devSessionRunId(subject),
        subject,
        capability: "run_command",
        now: new Date(),
      })
      expect(grant).not.toBeNull()
      expect(grant?.remainingUses).toBe(session.maxUses)
      expect(grant?.delegable).toBe(false)
    } finally {
      await db.close()
    }
  })

  it("formats enabled reply", () => {
    const text = formatDevSessionEnabledReply({
      expiresAt: new Date("2026-08-25T12:00:00Z"),
      maxUses: 50,
    })
    expect(text).toContain("开发模式")
    expect(text).toContain("50")
  })
})
