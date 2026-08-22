import { describe, expect, it } from "vitest"
import {
  defaultScheduleConversationId,
  evaluateScheduleTick,
  isQuietScheduleReply,
  scheduleIdempotencyKey,
  scheduleWindowStartMs,
  type ScheduleJobSpec,
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

describe("schedule tick math", () => {
  it("computes stable window and idempotency keys", () => {
    expect(scheduleWindowStartMs(125_000, 60_000)).toBe(120_000)
    expect(scheduleIdempotencyKey("heartbeat", 120_000)).toBe("schedule:heartbeat:120000")
    expect(defaultScheduleConversationId("heartbeat")).toBe("schedule-heartbeat")
  })

  it("fires when due and not busy", () => {
    const decision = evaluateScheduleTick({
      job: baseJob(),
      nowMs: 125_000,
      lastAttemptMs: null,
      conversationBusy: false,
      mainQueueBusy: false,
      scheduleInFlight: false,
    })
    expect(decision._tag).toBe("fire")
    if (decision._tag === "fire") {
      expect(decision.idempotencyKey).toBe("schedule:heartbeat:120000")
      expect(decision.deadline?.getTime()).toBe(125_000 + 120_000)
    }
  })

  it("skips during cooldown and after same-window fire", () => {
    expect(
      evaluateScheduleTick({
        job: baseJob(),
        nowMs: 125_000,
        lastAttemptMs: 110_000,
        conversationBusy: false,
        mainQueueBusy: false,
        scheduleInFlight: false,
      })._tag,
    ).toBe("skip")

    expect(
      evaluateScheduleTick({
        job: baseJob(),
        nowMs: 150_000,
        lastAttemptMs: 120_000,
        conversationBusy: false,
        mainQueueBusy: false,
        scheduleInFlight: false,
      }),
    ).toMatchObject({ _tag: "skip", reason: "already fired this window" })
  })

  it("defers when conversation or main queue is busy", () => {
    expect(
      evaluateScheduleTick({
        job: baseJob(),
        nowMs: 125_000,
        lastAttemptMs: null,
        conversationBusy: true,
        mainQueueBusy: false,
        scheduleInFlight: false,
      }),
    ).toMatchObject({ _tag: "defer", reason: "conversation busy" })

    expect(
      evaluateScheduleTick({
        job: baseJob(),
        nowMs: 125_000,
        lastAttemptMs: null,
        conversationBusy: false,
        mainQueueBusy: true,
        scheduleInFlight: false,
      }),
    ).toMatchObject({ _tag: "defer", reason: "main queue busy" })
  })

  it("detects quiet success replies", () => {
    expect(isQuietScheduleReply("", true)).toBe(true)
    expect(isQuietScheduleReply("无事", true)).toBe(true)
    expect(isQuietScheduleReply("需要审批", true)).toBe(false)
    expect(isQuietScheduleReply("", false)).toBe(false)
  })
})
