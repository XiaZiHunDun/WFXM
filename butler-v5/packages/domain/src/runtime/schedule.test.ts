import { describe, expect, it } from "vitest"
import {
  defaultScheduleConversationId,
  evaluateScheduleTick,
  isQuietScheduleReply,
  scheduleIdempotencyKey,
  scheduleWindowStartMs,
  type ScheduleJobSpec,
  type ScheduleTickDecision,
  type ScheduleTickInput,
} from "./schedule.js"

const baseJob = (): ScheduleJobSpec => ({
  id: "heartbeat",
  everyMs: 60_000,
  goal: "只读巡检",
  cooldownMs: 30_000,
  maxSteps: 3,
  deadlineMs: 120_000,
  quietSuccess: true,
  enabled: true,
})

function tick(overrides: Partial<ScheduleTickInput> & { job: ScheduleJobSpec }): ScheduleTickDecision {
  return evaluateScheduleTick({
    lastAttemptMs: null,
    conversationBusy: false,
    mainQueueBusy: false,
    scheduleInFlight: false,
    ...overrides,
  })
}

describe("schedule tick math", () => {
  it("computes stable window and idempotency keys", () => {
    expect(scheduleWindowStartMs(125_000, 60_000)).toBe(120_000)
    expect(scheduleIdempotencyKey("heartbeat", 120_000)).toBe("schedule:heartbeat:120000")
    expect(defaultScheduleConversationId("heartbeat")).toBe("schedule-heartbeat")
  })

  it("falls back to nowMs when everyMs is non-positive", () => {
    expect(scheduleWindowStartMs(1234, 0)).toBe(1234)
    expect(scheduleWindowStartMs(1234, -5)).toBe(1234)
  })

  it("fires when due, not busy, and computes a deadline from deadlineMs", () => {
    const decision = tick({ job: baseJob(), nowMs: 125_000 })
    expect(decision._tag).toBe("fire")
    if (decision._tag === "fire") {
      expect(decision.idempotencyKey).toBe("schedule:heartbeat:120000")
      expect(decision.deadline?.getTime()).toBe(125_000 + 120_000)
    }
  })

  it("fires with a null deadline when deadlineMs is null or non-positive", () => {
    const noDeadline = tick({ job: { ...baseJob(), deadlineMs: null }, nowMs: 125_000 })
    expect(noDeadline._tag).toBe("fire")
    if (noDeadline._tag === "fire") expect(noDeadline.deadline).toBeNull()

    const zeroDeadline = tick({ job: { ...baseJob(), deadlineMs: 0 }, nowMs: 125_000 })
    expect(zeroDeadline._tag).toBe("fire")
    if (zeroDeadline._tag === "fire") expect(zeroDeadline.deadline).toBeNull()
  })

  it("uses defaultScheduleConversationId when job has no conversationId", () => {
    const decision = tick({ job: baseJob(), nowMs: 125_000 })
    expect(decision._tag).toBe("fire")
    if (decision._tag === "fire") {
      expect(decision.conversationId).toBe("schedule-heartbeat")
    }
  })

  it("skips during cooldown and after same-window fire", () => {
    expect(
      tick({ job: baseJob(), nowMs: 125_000, lastAttemptMs: 110_000 })._tag,
    ).toBe("skip")

    expect(
      tick({ job: baseJob(), nowMs: 150_000, lastAttemptMs: 120_000 }),
    ).toMatchObject({ _tag: "skip", reason: "already fired this window" })
  })

  it("skips on validation failures (disabled, empty id/goal, non-positive everyMs)", () => {
    expect(tick({ job: { ...baseJob(), enabled: false }, nowMs: 0 })._tag).toBe("skip")
    expect(tick({ job: { ...baseJob(), id: "   " }, nowMs: 0 })).toMatchObject({
      _tag: "skip",
      reason: "empty job id",
    })
    expect(tick({ job: { ...baseJob(), goal: "" }, nowMs: 0 })).toMatchObject({
      _tag: "skip",
      reason: "empty goal",
    })
    expect(tick({ job: { ...baseJob(), everyMs: 0 }, nowMs: 0 })).toMatchObject({
      _tag: "skip",
      reason: "everyMs must be > 0",
    })
  })

  it("defers when conversation, main queue, or another schedule is in flight", () => {
    expect(tick({ job: baseJob(), conversationBusy: true })).toMatchObject({
      _tag: "defer",
      reason: "conversation busy",
    })
    expect(tick({ job: baseJob(), mainQueueBusy: true })).toMatchObject({
      _tag: "defer",
      reason: "main queue busy",
    })
    expect(tick({ job: baseJob(), scheduleInFlight: true })).toMatchObject({
      _tag: "defer",
      reason: "schedule in flight",
    })
  })

  it("detects quiet success replies", () => {
    expect(isQuietScheduleReply("", true)).toBe(true)
    expect(isQuietScheduleReply("ok", true)).toBe(true)
    expect(isQuietScheduleReply("quiet", true)).toBe(true)
    expect(isQuietScheduleReply("noop", true)).toBe(true)
    expect(isQuietScheduleReply("无事", true)).toBe(true)
    expect(isQuietScheduleReply("无异常", true)).toBe(true)
    expect(isQuietScheduleReply("quiet: no changes", true)).toBe(true)
    expect(isQuietScheduleReply("需要审批", true)).toBe(false)
    expect(isQuietScheduleReply("", false)).toBe(false)
    expect(isQuietScheduleReply("ok", false)).toBe(false)
    // leading/trailing whitespace is trimmed before comparison
    expect(isQuietScheduleReply("  ok  ", true)).toBe(true)
  })
})