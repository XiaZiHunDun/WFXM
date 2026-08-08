// domain/conversation/transitions.ts
// 对话状态机 — 纯函数，零副作用

import type {
  LoopId,
  ConversationEvent,
  ConversationState,
  Conversation,
  Turn,
  TurnId,
  ToolCallId,
} from "./types.js"

// ─── 对话聚合上的 Turn 转换 ──────────────────────────────
let turnSeq = 0
const newTurnId = (): TurnId => `turn-${++turnSeq}` as TurnId

export function submitUserMessage(c: Conversation, content: string): Conversation {
  if (c.status === "completed") {
    return c
  }
  const turn: Turn = {
    id: newTurnId(),
    status: "running",
    userMessage: {
      id: newTurnId(),
      conversationId: c.id,
      role: "user",
      content,
      createdAt: Date.now(),
    },
    assistantMessage: null,
    toolCallId: null,
    toolOutput: null,
  }
  return { ...c, status: "running" as const, turns: [...c.turns, turn] }
}

export function openTurn(c: Conversation, _input: { toolCallId: ToolCallId }): Conversation {
  if (c.turns.length === 0) {
    return c
  }
  const idx = c.turns.length - 1
  const cur = c.turns[idx]
  if (cur === undefined) {
    return c
  }
  const next: Turn = { ...cur, toolCallId: _input.toolCallId }
  const turns = c.turns.slice(0, idx).concat(next)
  return { ...c, turns }
}

export function applyToolResult(
  c: Conversation,
  input: { toolCallId: ToolCallId; output: string },
): Conversation {
  const idx = c.turns.findIndex((t) => t.toolCallId === input.toolCallId)
  if (idx < 0) {
    return c
  }
  const cur = c.turns[idx]
  if (cur === undefined) {
    return c
  }
  const next: Turn = { ...cur, toolOutput: input.output, status: "tooled" }
  const turns = c.turns.slice(0, idx).concat(next, c.turns.slice(idx + 1))
  return { ...c, turns }
}

// 辅助：从 Running 状态提取 loopId
function runningLoopId(state: ConversationState): LoopId | null {
  return state._tag === "Running" ? state.loopId : null
}

export function transition(state: ConversationState, event: ConversationEvent): ConversationState {
  switch (event._tag) {
    case "ConversationStarted":
      return state._tag === "Idle"
        ? { _tag: "Running", loopId: event.conversationId as unknown as LoopId }
        : state

    case "MessageAdded":
      // 消息添加不改变状态
      return state

    case "ToolCallStarted": {
      const loopId = runningLoopId(state)
      return loopId !== null
        ? { _tag: "AwaitingToolResult", toolCallId: event.toolCallId, loopId }
        : state
    }

    case "ToolCallCompleted":
      return state._tag === "AwaitingToolResult" && state.toolCallId === event.toolCallId
        ? { _tag: "Running", loopId: state.loopId }
        : state

    case "OwnerInputReceived":
      return state._tag === "AwaitingOwnerInput" ? { _tag: "Running", loopId: event.loopId } : state

    case "OwnerInputTimeout":
      return state._tag === "AwaitingOwnerInput"
        ? {
            _tag: "Failed",
            error: {
              _tag: "GuardRejected",
              reason: { _tag: "OwnerOffline", action: "OwnerInputTimeout" },
            },
          }
        : state

    case "ReviewRequested":
      return state._tag === "Running"
        ? { _tag: "AwaitingReview", receiptId: event.receiptId, reviewerAgent: event.reviewerAgent }
        : state

    case "ReviewCompleted":
      return state._tag === "AwaitingReview" && state.receiptId === event.receiptId
        ? event.approved
          ? { _tag: "Running", loopId: event.receiptId as unknown as LoopId }
          : {
              _tag: "Failed",
              error: {
                _tag: "GuardRejected",
                reason: { _tag: "VerificationLevelNotMet", required: "Standard" },
              },
            }
        : state

    case "ConversationCompleted":
      return event.receipt
        ? { _tag: "Completed" as const, receipt: event.receipt }
        : { _tag: "Completed" as const }

    case "ConversationFailed":
      return event.receipt
        ? { _tag: "Failed" as const, error: event.error, receipt: event.receipt }
        : { _tag: "Failed" as const, error: event.error }

    default:
      return state
  }
}
