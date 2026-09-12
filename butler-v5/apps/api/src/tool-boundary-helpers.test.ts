import { describe, expect, it, vi } from "vitest"
import type { ScopedGrantRecord } from "@butler/domain/governance/types.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import {
  markGrantConsumed,
  resolveOwnerSubject,
} from "./tool-boundary-helpers.js"

describe("tool-boundary-helpers (D58 T2 cycle break)", () => {
  it("module loads cleanly — no TDZ from broken cycle", async () => {
    // If the cycle is still in place via tool-boundary/approval-resume,
    // these would resolve to undefined when imported transitively.
    const toolBoundary = await import("./tool-boundary.js")
    expect(typeof toolBoundary.makeToolExecutor).toBe("function")
    expect(typeof toolBoundary.toolTimeoutMs).toBe("function")
    // D58 T2: resolveOwnerSubject moved to tool-boundary-helpers as part
    // of the cycle break. Confirm tool-boundary no longer re-exports it.
    expect((toolBoundary as Record<string, unknown>).resolveOwnerSubject).toBeUndefined()
    const approvalResume = await import("./approval-resume.js")
    // markGrantConsumed also moved; approval-resume should still re-export
    // approveWaitingStep/denyWaitingStep but no longer define markGrantConsumed.
    expect((approvalResume as Record<string, unknown>).markGrantConsumed).toBeUndefined()
  })

  it("resolveOwnerSubject returns fallback when env is unset", () => {
    expect(resolveOwnerSubject({}, "owner-fb")).toBe("owner-fb")
  })

  it("resolveOwnerSubject reads BUTLER_OWNER_WECHAT_ID first segment", () => {
    expect(resolveOwnerSubject({ BUTLER_OWNER_WECHAT_ID: "alice,bob" }, "fb")).toBe("alice")
    expect(resolveOwnerSubject({ BUTLER_OWNER_WECHAT_ID: "  alice  ,bob" }, "fb")).toBe("alice")
    expect(resolveOwnerSubject({ BUTLER_OWNER_WECHAT_ID: " , , " }, "fb")).toBe("fb")
  })

  it("markGrantConsumed no-ops when remainingUses is null (unlimited)", async () => {
    const update = vi.fn(async () => undefined)
    const store = { updateScopedGrantRemainingUses: update } as unknown as RuntimeStore
    const grant = { id: "g1", remainingUses: null } as unknown as ScopedGrantRecord
    await markGrantConsumed(store, grant)
    expect(update).not.toHaveBeenCalled()
  })

  it("markGrantConsumed decrements remainingUses and clamps at 0", async () => {
    const update = vi.fn(async () => undefined)
    const store = { updateScopedGrantRemainingUses: update } as unknown as RuntimeStore
    const grant = { id: "g2", remainingUses: 1 } as unknown as ScopedGrantRecord
    await markGrantConsumed(store, grant)
    expect(update).toHaveBeenCalledWith("g2", 0)
  })
})
