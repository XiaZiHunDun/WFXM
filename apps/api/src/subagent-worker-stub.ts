/**
 * D75 T1 (CQ-002): extract the "no LLM adapter" stub-reply path from
 * handleOutboxMessage.
 *
 * When the worker boots without a configured LLM provider (test envs,
 * partial-bootstrap scenarios), `Delegate` outbox messages are short-
 * circuited with a fixed Chinese stub reply rather than failing the
 * outbox claim. The path composes:
 *   - bridge.appendConversationEvent(AssistantMessageProduced)
 *   - finalizeChildRun(runtimeStore, childRunId, { ok: false, ... })
 *   - pushEventToSubscribers(streamId, ...)
 *
 * Extracted so handleOutboxMessage's main LLM path doesn't carry this
 * 41-line branch inline.
 */
import type { EventBridge } from "@butler/persistence/event-bridge.js"
import type { OutboxMessage } from "@butler/persistence/outbox.js"
import type { RuntimeStore } from "@butler/domain/runtime.js"
import { pushEventToSubscribers } from "./ws-routes.js"
import { finalizeChildRun, prefixReply, type SubagentWorkerLogger } from "./subagent-worker.js"

const STUB_CONTENT = "（子代理未配置 LLM，无法执行）"

/**
 * Write the no-adapter stub reply for a `Delegate` outbox message.
 * Idempotent on the bridge side; best-effort on the finalize / push
 * side (errors are logged via `logger.warn` rather than thrown so the
 * outbox claim still resolves and the message is marked delivered).
 */
export async function writeChildStubReply(args: {
  readonly bridge: EventBridge
  readonly msg: OutboxMessage
  readonly childConversationId: string
  readonly role: string
  readonly runtimeStore: RuntimeStore | undefined
  readonly childRunId: string | null
  readonly logger: SubagentWorkerLogger
}): Promise<void> {
  args.logger.warn(
    `[subagent-worker] no LLM adapter configured; writing stub reply for child ${args.childConversationId}`,
  )
  const stubEvent = {
    streamId: args.msg.streamId,
    eventId: crypto.randomUUID(),
    eventType: "AssistantMessageProduced" as const,
    correlationId: crypto.randomUUID(),
    actor: { kind: "agent" as const, id: `subagent-${args.role}` },
    event: {
      _tag: "AssistantMessageProduced" as const,
      content: prefixReply(args.role, STUB_CONTENT),
    },
  }
  await args.bridge.appendConversationEvent(stubEvent)
  if (args.runtimeStore && args.childRunId) {
    try {
      await finalizeChildRun(args.runtimeStore, args.childRunId, {
        ok: false,
        reply: STUB_CONTENT,
        role: args.role,
      })
    } catch (err) {
      args.logger.warn(
        `[subagent-worker] failed to finalize child run ${args.childRunId}: ${
          err instanceof Error ? err.message : String(err)
        }`,
      )
    }
  }
  // R8.x.8: push the reply to any WS clients subscribed to the
  // parent conversation. pushEventToSubscribers is a no-op when
  // nobody is listening, so this is safe to call unconditionally.
  pushEventToSubscribers(args.msg.streamId, {
    eventType: stubEvent.eventType,
    event: stubEvent.event,
    eventId: stubEvent.eventId,
  })
}
