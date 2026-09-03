// domain/workflows/types.ts
// 工作流域 ADT — Channel 抽象、变更分类、Send API

import type { LoopError } from "../errors.js"
import type { CommandSpec } from "../tools/types.js"

// ─── 品牌类型 ───────────────────────────────────────────
export type WorkflowId = string & { readonly __brand: "WorkflowId" }
export type WorkflowStepId = string & { readonly __brand: "WorkflowStepId" }

// ─── Channel 抽象 [OPT-1] ──────────────────────────────
export type Channel<T> = {
  readonly id: string
  readonly state: T
  readonly suspended: boolean
}

// ─── 变更类型分类 [OPT-4] ──────────────────────────────
export type ChangeType =
  | { readonly _tag: "Added"; readonly path: string }
  | { readonly _tag: "Modified"; readonly path: string; readonly diff: string }
  | { readonly _tag: "Removed"; readonly path: string; readonly reason: string }

// ─── Send API [OPT-11] ─────────────────────────────────
export type SendCommand = {
  readonly toAgent: string
  readonly message: string
  readonly contextRef?: string
}

// ─── 工作流状态 ─────────────────────────────────────────
export type WorkflowState =
  | { readonly _tag: "NotStarted" }
  | { readonly _tag: "Running"; readonly channels: readonly Channel<unknown>[] }
  | { readonly _tag: "AwaitingMerge"; readonly results: readonly unknown[] }
  | { readonly _tag: "Completed"; readonly outputs: readonly unknown[] }
  | { readonly _tag: "Failed"; readonly error: LoopError }

// ─── Workflow 事件 ──────────────────────────────────────
export type WorkflowEvent =
  | { readonly _tag: "WorkflowStarted"; readonly workflowId: WorkflowId }
  | { readonly _tag: "ChannelCreated"; readonly channelId: string }
  | { readonly _tag: "ChannelCompleted"; readonly channelId: string; readonly result: unknown }
  | { readonly _tag: "ChannelsMerged"; readonly results: readonly unknown[] }
  | { readonly _tag: "WorkflowCompleted"; readonly outputs: readonly unknown[] }
  | { readonly _tag: "WorkflowFailed"; readonly error: LoopError }

// ─── R2.2 生命周期状态机 [spec §5.2] ────────────────────
// 状态机：pending → running ⇄ waiting_approval → completed / failed
export type WorkflowStatus = "pending" | "running" | "waiting_approval" | "completed" | "failed"

// 步骤判别联合（tool / approval / delegate）
export type WorkflowStep =
  | {
      readonly id: WorkflowStepId
      readonly kind: "tool"
      readonly spec: CommandSpec
    }
  | {
      readonly id: WorkflowStepId
      readonly kind: "approval"
      readonly approver: string
    }
  | {
      readonly id: WorkflowStepId
      readonly kind: "delegate"
      readonly role: string
    }

// 一次完整工作流运行
export interface WorkflowRun {
  readonly id: WorkflowId
  readonly status: WorkflowStatus
  readonly steps: readonly WorkflowStep[]
  readonly currentStepId: WorkflowStepId | null
  readonly error: string | null
}
