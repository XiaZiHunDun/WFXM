import type { Run, RunStatus } from "./types.js"

export type RunTransitionResult =
  | { readonly _tag: "TransitionAccepted"; readonly run: Run }
  | {
      readonly _tag: "TransitionRejected"
      readonly run: Run
      readonly from: RunStatus
      readonly to: RunStatus
    }

const LEGAL_TRANSITIONS: Readonly<Record<RunStatus, readonly RunStatus[]>> = {
  queued: ["running", "cancelled", "expired"],
  running: ["waiting_approval", "waiting_external", "succeeded", "failed", "cancelled", "expired"],
  waiting_approval: ["running", "failed", "cancelled", "expired"],
  waiting_external: ["running", "failed", "cancelled", "expired"],
  succeeded: [],
  failed: [],
  cancelled: [],
  expired: [],
}

/**
 * SSOT for terminal Run statuses: exactly the statuses with **no outgoing
 * edges** in `LEGAL_TRANSITIONS`. Terminal runs cannot transition to anything,
 * including themselves. Consumers must derive terminal-ness from these helpers
 * rather than re-hardcoding the status list.
 */
export const TERMINAL_RUN_STATUSES = (
  Object.entries(LEGAL_TRANSITIONS)
    .filter(([, targets]) => targets.length === 0)
    .map(([status]) => status as RunStatus)
) satisfies readonly RunStatus[]

export function isTerminalRunStatus(status: RunStatus): boolean {
  return TERMINAL_RUN_STATUSES.includes(status)
}

// ─── Pure Run state transitions ──────────────────────────
export function canTransitionRun(from: RunStatus, to: RunStatus): boolean {
  return LEGAL_TRANSITIONS[from].includes(to)
}

export function transitionRun(run: Run, to: RunStatus, updatedAt: number): RunTransitionResult {
  if (!canTransitionRun(run.status, to)) {
    return {
      _tag: "TransitionRejected",
      run,
      from: run.status,
      to,
    }
  }

  return {
    _tag: "TransitionAccepted",
    run: {
      ...run,
      status: to,
      version: run.version + 1,
      updatedAt,
    },
  }
}
