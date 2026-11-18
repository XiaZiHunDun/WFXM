// domain/event-sourcing.test.ts
// 事件溯源 + CQRS 纯函数测试

import { describe, it, expect } from "vitest"
import {
  projectConversation,
  loadConversation,
  delta,
  buildEnvelope,
  validateEnvelope,
  type DomainEvent,
  type StreamType,
} from "./event-sourcing.js"
import type { ConversationEvent, ConversationId } from "./conversation/types.js"

const cid: ConversationId = "conv-1" as ConversationId

describe("domain/event-sourcing", () => {
  describe("projectConversation", () => {
    it("空事件列表返回 Idle 状态", () => {
      const state = projectConversation([])
      expect(state._tag).toBe("Idle")
    })

    it("单事件 ConversationStarted 投影到 Idle", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
      ]
      const state = projectConversation(events)
      expect(state._tag).toBeDefined()
    })

    it("多事件投影链路完整", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
        {
          _tag: "MessageAdded",
          message: { role: "user", content: "hello", timestamp: Date.now() },
        },
        { _tag: "ToolCallStarted", toolCallId: "t1" },
        { _tag: "ToolCallCompleted", toolCallId: "t1", result: "data" },
        {
          _tag: "MessageAdded",
          message: { role: "assistant", content: "done", timestamp: Date.now() },
        },
        { _tag: "ConversationCompleted" },
      ]
      const state = projectConversation(events)
      // 最终状态应该是 Completed
      expect(state._tag).toBe("Completed")
    })
  })

  describe("loadConversation", () => {
    it("等同于 projectConversation", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
      ]
      expect(loadConversation(events)).toEqual(projectConversation(events))
    })
  })

  describe("delta", () => {
    it("从 lastVersion 之后返回事件", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
        { _tag: "MessageAdded", message: { role: "user", content: "a", timestamp: 1 } },
        { _tag: "MessageAdded", message: { role: "user", content: "b", timestamp: 2 } },
      ]
      const result = delta({ streamId: "s1", lastVersion: 1 }, events)
      expect(result.length).toBe(2)
    })

    it("lastVersion=0 返回全部事件", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
      ]
      const result = delta({ streamId: "s1", lastVersion: 0 }, events)
      expect(result.length).toBe(1)
    })

    it("lastVersion 超出范围返回空数组", () => {
      const events: readonly ConversationEvent[] = [
        { _tag: "ConversationStarted", conversationId: cid },
      ]
      const result = delta({ streamId: "s1", lastVersion: 10 }, events)
      expect(result.length).toBe(0)
    })
  })

  // ─── R2.3 Event Envelope ───────────────────────────────
  describe("event envelope", () => {
    const ev: DomainEvent = { _tag: "ConversationStarted" } as DomainEvent
    it("builds a valid envelope", () => {
      const env = buildEnvelope({
        streamId: "s-1",
        streamType: "conversation" as StreamType,
        event: ev,
      })
      expect(env.streamId).toBe("s-1")
      expect(env.eventVersion).toBe(1)
      expect(env.eventType).toBe("ConversationStarted")
      expect(env.streamType).toBe("conversation")
      expect(env.correlationId).toBeTruthy()
      expect(env.actor.kind).toBe("system")
      const validation = validateEnvelope(env)
      expect(validation.ok).toBe(true)
    })
    it("rejects unknown envelope version", () => {
      const env = buildEnvelope({
        streamId: "s-1",
        streamType: "conversation" as StreamType,
        event: ev,
      })
      const broken = { ...env, eventVersion: 99 }
      const validation = validateEnvelope(broken)
      expect(validation.ok).toBe(false)
      if (!validation.ok) {
        expect(validation.reason).toMatch(/eventVersion/)
      }
    })
    it("rejects streamVersion < 1", () => {
      const env = buildEnvelope({
        streamId: "s-1",
        streamType: "conversation" as StreamType,
        event: ev,
      })
      const broken = { ...env, streamVersion: 0 }
      expect(validateEnvelope(broken).ok).toBe(false)
    })
    it("rejects missing correlationId", () => {
      const env = buildEnvelope({
        streamId: "s-1",
        streamType: "conversation" as StreamType,
        event: ev,
      })
      const broken = { ...env, correlationId: "" }
      expect(validateEnvelope(broken).ok).toBe(false)
    })
  })
})
