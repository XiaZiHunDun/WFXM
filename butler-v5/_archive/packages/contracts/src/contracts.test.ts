import { describe, expect, it } from "vitest"
import type { PluginManifest } from "./plugin.js"
import type { StartConversationRequest, StartConversationResponse } from "./api.js"
import type { EventBatchResponse, EventSubscribeRequest } from "./events.js"

describe("contracts shape", () => {
  it("StartConversationRequest/Response compile", () => {
    const req: StartConversationRequest = {
      apiVersion: "v1",
      projectId: "p1",
      toolName: null,
      content: "hi",
    }
    const res: StartConversationResponse = { conversationId: "c1", turnId: "t1" }
    expect(req.apiVersion).toBe("v1")
    expect(res.turnId).toBe("t1")
  })
  it("PluginManifest enforces trust enum", () => {
    const m: PluginManifest = {
      name: "demo",
      version: "0.0.1",
      trust: "bundled",
      provides: ["tool"],
      tools: [],
      requiredCapabilities: [],
      signature: "ok",
    }
    expect(m.trust).toBe("bundled")
  })
  it("EventSubscribeRequest/Response compile", () => {
    const r: EventSubscribeRequest = { streamTypes: ["conversation"], fromVersion: 1 }
    const b: EventBatchResponse = { events: [], nextVersion: 1 }
    expect(b.nextVersion).toBe(1)
    expect(r.streamTypes).toContain("conversation")
  })
})
