import { describe, expect, it } from "vitest"
import {
  canTransitionRun,
  isTerminalRunStatus,
  TERMINAL_RUN_STATUSES,
  transitionRun,
  type Run,
  type RunStatus,
} from "./index.js"
import { isActiveMainRunStatus } from "./store-contract.js"

const baseRun: Run = {
  id: "run-1",
  conversationId: "conversation-1",
  parentRunId: null,
  trigger: {
    subject: "owner-1",
    source: "channel",
    conversationRef: "conversation-1",
    payload: { text: "hello" },
    trustLevel: "trusted",
    idempotencyKey: "inbound-1",
  },
  goal: "reply",
  budget: { maxSteps: 5 },
  deadline: null,
  status: "queued",
  version: 1,
  createdAt: 1,
  updatedAt: 1,
}

const ALL_STATUSES: readonly RunStatus[] = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_external",
  "succeeded",
  "failed",
  "cancelled",
  "expired",
]

const ACTIVE_STATUSES: readonly RunStatus[] = [
  "queued",
  "running",
  "waiting_approval",
  "waiting_external",
]

const TERMINAL_STATUSES: readonly RunStatus[] = [
  "succeeded",
  "failed",
  "cancelled",
  "expired",
]

// Exhaustive from/to rules of the Run state machine (the frozen contract spec).
// Every entry below must hold; any drift from transitions.ts is an inconsistency.
const EXPECTED_LEGAL: Readonly<Record<RunStatus, readonly RunStatus[]>> = {
  queued: ["running", "cancelled", "expired"],
  running: [
    "waiting_approval",
    "waiting_external",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
  ],
  waiting_approval: ["running", "failed", "cancelled", "expired"],
  waiting_external: ["running", "failed", "cancelled", "expired"],
  succeeded: [],
  failed: [],
  cancelled: [],
  expired: [],
}

function makeRun(status: RunStatus): Run {
  return { ...baseRun, status }
}

describe("runtime Run transitions", () => {
  it.each(ALL_STATUSES)(
    "exposes the exact allowed-target set for %s (accepts legal, rejects everything else)",
    (from) => {
      const expected = EXPECTED_LEGAL[from]
      for (const to of ALL_STATUSES) {
        expect(canTransitionRun(from, to), `${from} -> ${to}`).toBe(
          expected.includes(to),
        )
      }
    },
  )

  it("covers the deadline branch: every active status may expire, terminals may not", () => {
    for (const from of ACTIVE_STATUSES) {
      expect(canTransitionRun(from, "expired"), `${from} -> expired`).toBe(true)
    }
    for (const from of TERMINAL_STATUSES) {
      expect(canTransitionRun(from, "expired"), `${from} -> expired`).toBe(false)
    }
  })

  it("covers the cancelled branch: every active status may cancel, terminals may not", () => {
    for (const from of ACTIVE_STATUSES) {
      expect(canTransitionRun(from, "cancelled"), `${from} -> cancelled`).toBe(true)
    }
    for (const from of TERMINAL_STATUSES) {
      expect(canTransitionRun(from, "cancelled"), `${from} -> cancelled`).toBe(false)
    }
  })

  it("covers the waiting_approval branch (enter, resume, and no short-circuit to success)", () => {
    expect(canTransitionRun("running", "waiting_approval")).toBe(true)
    expect(canTransitionRun("waiting_approval", "running")).toBe(true)
    // approval must resume via running before succeeding/publishing
    expect(canTransitionRun("waiting_approval", "succeeded")).toBe(false)
    expect(canTransitionRun("waiting_approval", "waiting_external")).toBe(false)
  })

  it("returns a new versioned Run for a legal transition", () => {
    const result = transitionRun(baseRun, "running", 2)

    expect(result).toEqual({
      _tag: "TransitionAccepted",
      run: { ...baseRun, status: "running", version: 2, updatedAt: 2 },
    })
  })

  it("preserves the Run (no version bump, no mutation) when a transition is illegal", () => {
    const result = transitionRun(makeRun("queued"), "succeeded", 2)

    expect(result).toEqual({
      _tag: "TransitionRejected",
      run: makeRun("queued"),
      from: "queued",
      to: "succeeded",
    })
    expect(result.run.version).toBe(1)
    expect(result.run.status).toBe("queued")
  })

  it("rejects every illegal from/to pair across the full matrix via transitionRun", () => {
    for (const from of ALL_STATUSES) {
      for (const to of ALL_STATUSES) {
        const legal = EXPECTED_LEGAL[from].includes(to)
        const result = transitionRun(makeRun(from), to, 99)
        if (legal) {
          expect(result._tag, `${from} -> ${to}`).toBe("TransitionAccepted")
          if (result._tag === "TransitionAccepted") {
            expect(result.run.status).toBe(to)
            expect(result.run.version).toBe(2) // baseRun.version(1) + 1
          }
        } else {
          expect(result._tag, `${from} -> ${to}`).toBe("TransitionRejected")
        }
      }
    }
  })

  it("rejects any transition out of terminal states, including self-transitions", () => {
    for (const terminal of TERMINAL_STATUSES) {
      for (const to of ALL_STATUSES) {
        expect(canTransitionRun(terminal, to)).toBe(false)
      }
    }
  })

  it("exposes exactly the no-out-edge statuses as terminal (SSOT consistency)", () => {
    const expected = ALL_STATUSES.filter((s) => EXPECTED_LEGAL[s].length === 0)
    expect([...TERMINAL_RUN_STATUSES].sort()).toEqual([...expected].sort())
  })

  it.each(TERMINAL_STATUSES)("marks %s as terminal", (status) => {
    expect(isTerminalRunStatus(status)).toBe(true)
  })

  it.each(ACTIVE_STATUSES)("marks %s as non-terminal", (status) => {
    expect(isTerminalRunStatus(status)).toBe(false)
  })

  it("agrees terminal-ness with the transition matrix", () => {
    for (const from of ALL_STATUSES) {
      const noOutgoingEdges = EXPECTED_LEGAL[from].length === 0
      expect(isTerminalRunStatus(from), from).toBe(noOutgoingEdges)
    }
  })
})
describe("state-machine status partition (SSOT consistency)", () => {
  const allStatuses: RunStatus[] = [
    "queued",
    "running",
    "waiting_approval",
    "waiting_external",
    "succeeded",
    "failed",
    "cancelled",
    "expired",
  ]

  it("splits every RunStatus into exactly {active-main} or {terminal}", () => {
    for (const s of allStatuses) {
      expect(isActiveMainRunStatus(s) || isTerminalRunStatus(s), s).toBe(true)
      expect(isActiveMainRunStatus(s) && isTerminalRunStatus(s), s).toBe(false)
    }
  })
})
