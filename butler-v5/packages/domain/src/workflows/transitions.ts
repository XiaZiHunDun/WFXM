// domain/workflows/transitions.ts
// 工作流状态机 — 纯函数

import type {
  WorkflowEvent,
  WorkflowId,
  WorkflowRun,
  WorkflowState,
  WorkflowStep,
  WorkflowStepId,
} from "./types.js"

export function workflowTransition(state: WorkflowState, event: WorkflowEvent): WorkflowState {
  switch (event._tag) {
    case "WorkflowStarted":
      return state._tag === "NotStarted" ? { _tag: "Running", channels: [] } : state

    case "ChannelCreated":
      return state._tag === "Running"
        ? {
            ...state,
            channels: [...state.channels, { id: event.channelId, state: null, suspended: false }],
          }
        : state

    case "ChannelCompleted":
      return state._tag === "Running"
        ? {
            ...state,
            channels: state.channels.map((ch) =>
              ch.id === event.channelId ? { ...ch, state: event.result } : ch,
            ),
          }
        : state

    case "ChannelsMerged":
      return state._tag === "Running" ? { _tag: "AwaitingMerge", results: event.results } : state

    case "WorkflowCompleted":
      return { _tag: "Completed", outputs: event.outputs }

    case "WorkflowFailed":
      return { _tag: "Failed", error: event.error }

    default:
      return state
  }
}

// ─── R2.2 生命周期状态机纯函数 [spec §5.2] ──────────────
// 不使用 throw；违反前置条件时返回 no-op（遵循现有 workflowTransition 风格）

// 启动工作流：至少需要一个步骤；空步骤视为 no-op
export function startWorkflow(id: WorkflowId, steps: readonly WorkflowStep[]): WorkflowRun {
  if (steps.length === 0) {
    return {
      id,
      status: "pending",
      steps,
      currentStepId: null,
      error: "工作流至少需要一个步骤",
    }
  }
  return {
    id,
    status: "pending",
    steps,
    currentStepId: null,
    error: null,
  }
}

// pending → running；其它状态为 no-op
export function pendingWorkflow(w: WorkflowRun): WorkflowRun {
  if (w.status === "completed" || w.status === "failed") {
    return w
  }
  return { ...w, status: "running" }
}

// 推进到指定步骤的下一位；最后一步完成后切到 completed
export function advanceStep(w: WorkflowRun, stepId: WorkflowStepId): WorkflowRun {
  const idx = w.steps.findIndex((s) => s.id === stepId)
  if (idx < 0) {
    return { ...w, error: `step not found: ${String(stepId)}` }
  }
  if (idx + 1 >= w.steps.length) {
    return { ...w, status: "completed", currentStepId: null, error: null }
  }
  const next = w.steps[idx + 1]
  if (!next) {
    return { ...w, status: "completed", currentStepId: null, error: null }
  }
  return { ...w, status: "running", currentStepId: next.id, error: null }
}

// 等待审批：仅在目标步骤存在时切到 waiting_approval
export function waitForApproval(
  w: WorkflowRun,
  stepId: WorkflowStepId,
  _approver: string,
): WorkflowRun {
  if (!w.steps.find((s) => s.id === stepId)) {
    return { ...w, error: `step not found: ${String(stepId)}` }
  }
  return { ...w, status: "waiting_approval", currentStepId: stepId, error: null }
}

// 终止：任何状态下都可失败
export function failWorkflow(w: WorkflowRun, error: string): WorkflowRun {
  return { ...w, status: "failed", error }
}
