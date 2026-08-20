import { describe, expect, it } from "vitest"
import { makeToolExecutor, resolveOwnerSubject } from "./tool-boundary.js"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"

describe("tool-boundary", () => {
  it("resolveOwnerSubject prefers BUTLER_OWNER_WECHAT_ID", () => {
    expect(
      resolveOwnerSubject({ BUTLER_OWNER_WECHAT_ID: "owner-a, owner-b" }, "fallback"),
    ).toBe("owner-a")
    expect(resolveOwnerSubject({}, "fallback")).toBe("fallback")
  })

  it("makeToolExecutor routes through policy gate", async () => {
    const def: ToolDefinition = {
      name: "get_current_time" as ToolDefinition["name"],
      risk: "low",
      run: async () => ({ ok: true, output: "t" }),
    }
    const executor = makeToolExecutor({
      tools: [def],
      ownerSubject: "owner-1",
      subject: "guest-1",
      conversationId: "conv-1",
      timeoutMsFor: () => 1000,
    })
    const result = await executor.execute(def, {})
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.output).toBe("t")
    }
  })
})
