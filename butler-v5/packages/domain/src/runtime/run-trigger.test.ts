import { describe, expect, it } from "vitest"
import {
  buildApiRunTrigger,
  buildChannelRunTrigger,
  buildRunTrigger,
  buildTaskRunTrigger,
  buildWechatRunTrigger,
  runBudgetWithTrigger,
  validateRunTrigger,
} from "./run-trigger.js"
import { buildScheduleRunTrigger } from "./schedule.js"

describe("RunTrigger builders", () => {
  it("builds wechat channel trigger", () => {
    const trigger = buildWechatRunTrigger({
      userId: "wx-u1",
      conversationId: "c-wx-1",
      content: "hi",
      messageId: "msg-1",
    })
    expect(trigger.source).toBe("channel")
    expect(trigger.trustLevel).toBe("trusted")
    expect(trigger.idempotencyKey).toBe("msg-1")
  })

  it("merges extraPayload into wechat trigger", () => {
    const trigger = buildWechatRunTrigger({
      userId: "wx-u1",
      conversationId: "c-wx-1",
      content: "dev task",
      extraPayload: { workingSetMode: "dev" },
    })
    expect(trigger.payload).toMatchObject({
      channelId: "wechat",
      content: "dev task",
      workingSetMode: "dev",
    })
  })

  it("builds slack/telegram webhook trigger", () => {
    const trigger = buildChannelRunTrigger({
      channelId: "slack",
      fromSubject: "U1",
      conversationId: "c-ch-slack-U1",
      content: "hello",
      messageId: "slack-1",
    })
    expect(trigger.source).toBe("webhook")
    expect(trigger.payload).toEqual({ channelId: "slack", content: "hello" })
  })

  it("validates required fields", () => {
    const trigger = buildApiRunTrigger({
      subject: "owner",
      idempotencyKey: "k1",
    })
    expect(validateRunTrigger(trigger)).toEqual({ ok: true })
    expect(
      validateRunTrigger({ ...trigger, idempotencyKey: "" }),
    ).toEqual({ ok: false, reason: "idempotencyKey is required" })
  })

  it("merges trigger metadata into run budget", () => {
    const trigger = buildWechatRunTrigger({
      userId: "wx-u1",
      conversationId: "c-1",
      content: "hi",
    })
    expect(runBudgetWithTrigger(trigger)).toMatchObject({
      maxSteps: 5,
      trustLevel: "trusted",
      triggerPayload: { channelId: "wechat", content: "hi" },
      conversationRef: "c-1",
    })
  })

  it("builds schedule trigger as system:scheduler", () => {
    const trigger = buildScheduleRunTrigger({
      jobId: "heartbeat",
      goal: "巡检",
      conversationId: "schedule-heartbeat",
      idempotencyKey: "schedule:heartbeat:1",
      everyMs: 3600_000,
    })
    expect(trigger.source).toBe("schedule")
    expect(trigger.subject).toBe("system:scheduler")
    expect(trigger.trustLevel).toBe("trusted")
    expect(validateRunTrigger(trigger)).toEqual({ ok: true })
  })

  it("builds task trigger with owner trust", () => {
    const trigger = buildTaskRunTrigger({
      subject: "owner",
      taskId: "t1",
      goal: "do work",
      conversationId: "task-t1",
      idempotencyKey: "task:t1:1",
      procedureId: "p1",
      stepKey: "check",
    })
    expect(trigger.source).toBe("task")
    expect(trigger.trustLevel).toBe("owner")
    expect(trigger.payload).toMatchObject({ taskId: "t1", stepKey: "check" })
    expect(validateRunTrigger(trigger)).toEqual({ ok: true })
  })
})

describe("RunTrigger normalization boundaries", () => {
  it("normalizes whitespace on subject and idempotencyKey in the full run trigger", () => {
    const trigger = buildRunTrigger({
      subject: "  owner-1  ",
      source: "api",
      idempotencyKey: "  k-1  ",
    })
    expect(trigger.subject).toBe("owner-1")
    expect(trigger.idempotencyKey).toBe("k-1")
  })

  it("defaults conversationRef to null, payload to {}, trustLevel to untrusted", () => {
    const trigger = buildRunTrigger({ subject: "owner", source: "api", idempotencyKey: "k" })
    expect(trigger.conversationRef).toBeNull()
    expect(trigger.payload).toEqual({})
    expect(trigger.trustLevel).toBe("untrusted")
  })

  it("rejects a subject that is empty after normalization", () => {
    const trigger = buildRunTrigger({ subject: "   ", source: "api", idempotencyKey: "k" })
    expect(validateRunTrigger(trigger)).toEqual({
      ok: false,
      reason: "subject is required",
    })
  })

  it("rejects an idempotencyKey that is empty after normalization", () => {
    const trigger = buildRunTrigger({ subject: "owner", source: "api", idempotencyKey: "  " })
    expect(validateRunTrigger(trigger)).toEqual({
      ok: false,
      reason: "idempotencyKey is required",
    })
  })

  it("enforces conversationRef only for channel/webhook full-run entry, not other sources", () => {
    const noRef = { subject: "u", idempotencyKey: "k" } as const
    for (const source of ["channel", "webhook"] as const) {
      expect(
        validateRunTrigger(buildRunTrigger({ ...noRef, source })),
        source,
      ).toEqual({
        ok: false,
        reason: "conversationRef is required for channel/webhook triggers",
      })
    }
    // A parent_run (child) trigger — like a full run via api/cli/schedule/task —
    // does not require conversationRef.
    for (const source of ["api", "cli", "schedule", "task", "parent_run"] as const) {
      expect(validateRunTrigger(buildRunTrigger({ ...noRef, source })), source).toEqual({
        ok: true,
      })
    }
  })

  it("inherits a parent-run budget default of maxSteps 5 without clobbering base overrides", () => {
    const trigger = buildRunTrigger({ subject: "owner", source: "api", idempotencyKey: "k" })
    expect(runBudgetWithTrigger(trigger)).toMatchObject({ maxSteps: 5 })
    expect(runBudgetWithTrigger(trigger, { maxSteps: 9 })).toMatchObject({ maxSteps: 9 })
  })

  it("normalizes a task (parent-run child) trigger with conditional payload fields", () => {
    const bare = buildTaskRunTrigger({
      subject: " owner ",
      taskId: "t1",
      goal: "work",
      conversationId: "c1",
      idempotencyKey: " k ",
    })
    expect(bare.subject).toBe("owner")
    expect(bare.idempotencyKey).toBe("k")
    expect(bare.payload).toEqual({ taskId: "t1", goal: "work" })
    // procedureId/stepKey are omitted entirely unless provided.
    expect("procedureId" in bare.payload).toBe(false)
    expect("stepKey" in bare.payload).toBe(false)

    const full = buildTaskRunTrigger({
      subject: "owner",
      taskId: "t1",
      goal: "work",
      conversationId: "c1",
      idempotencyKey: "k",
      procedureId: "p1",
      stepKey: "check",
    })
    expect(full.payload).toMatchObject({ procedureId: "p1", stepKey: "check" })
    expect(validateRunTrigger(full)).toEqual({ ok: true })
  })
})