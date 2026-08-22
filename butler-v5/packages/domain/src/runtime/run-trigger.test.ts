import { describe, expect, it } from "vitest"
import {
  buildApiRunTrigger,
  buildChannelRunTrigger,
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
