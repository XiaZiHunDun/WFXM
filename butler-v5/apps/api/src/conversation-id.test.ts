/**
 * @deprecated Tests live in `packages/runtime/src/intake/conversation-id.test.ts`.
 * Kept as a thin re-export suite so apps/api path still covers the shim.
 */
import { describe, expect, it } from "vitest"
import {
  CONVERSATION_ID_MAX_LEN,
  defaultWechatConversationId,
  parseClientConversationId,
} from "@butler/runtime/intake/index.js"

describe("conversation-id shim (apps/api)", () => {
  it("re-exports parse + default helpers", () => {
    expect(parseClientConversationId("c-ok").kind).toBe("valid")
    expect(defaultWechatConversationId("wechat", "u1")).toBe("c-wechat-u1")
    expect(CONVERSATION_ID_MAX_LEN).toBe(128)
  })
})
