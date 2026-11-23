/**
 * Acceptance: weekly digest — slash command and scheduled push share numbers.
 * No real WeChat: the push goes to the mock outbox.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterAll, beforeAll, describe, expect, it } from "vitest"
import { runWeeklyDigestTick } from "@butler/api/weekly-digest-worker.js"
import { makeAcceptanceApp, sendWechatMessage, type AcceptanceApp } from "../harness.js"

describe("acceptance/weekly-digest (手动 /周报 → 自动推送)", () => {
  let app: AcceptanceApp
  let dir: string
  let outbox: string
  const previousOutbox = process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"]

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "weekly-digest-acceptance-"))
    outbox = join(dir, "outbox.jsonl")
    process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] = outbox
    app = await makeAcceptanceApp()
  })

  afterAll(async () => {
    await app.close()
    rmSync(dir, { recursive: true, force: true })
    if (previousOutbox === undefined) delete process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"]
    else process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] = previousOutbox
  })

  it("counts a completed task and an approval, then pushes once", async () => {
    const added = await sendWechatMessage(app, { content: "/待办 新增 本周完成" })
    expect(added.reply).toContain("已添加待办")

    const store = app.wiring.taskStore
    if (!store) throw new Error("task store missing")
    const tasks = await store.listBySubject({ subject: "u-owner" })
    const task = tasks.find((item) => item.title.includes("本周完成"))
    if (!task) throw new Error("task not persisted")

    const done = await sendWechatMessage(app, {
      content: `/完成 ${task.id.slice(0, 8)} 确认`,
    })
    expect(done.reply).toContain("已标记完成")

    await app.wiring.runtimeStore.appendAuditEvent({
      auditId: crypto.randomUUID(),
      runId: null,
      conversationId: null,
      action: "approval.requested",
      subject: "u-owner",
      detail: {},
      createdAt: new Date(),
      actor: "owner-direct",
    })

    const manual = await sendWechatMessage(app, { content: "/周报" })
    expect(manual.reply).toContain("完成 1 项")
    expect(manual.reply).toContain("待办 0 项")
    expect(manual.reply).toContain("失败 0 次")
    expect(manual.reply).toContain("审批 1 次")

    // Scheduled push at "now" (Asia/Shanghai) must produce the same structure.
    const now = Date.now()
    const shanghai = new Date(now + 8 * 3600_000)
    const result = await runWeeklyDigestTick({
      wiring: app.wiring,
      env: process.env,
      nowMs: () => now,
      config: {
        enabled: true,
        to: "u-owner",
        weekday: shanghai.getUTCDay(),
        hour: shanghai.getUTCHours(),
        minute: shanghai.getUTCMinutes(),
        tickMs: 60_000,
      },
    })
    expect(result.sent).toBe(true)
    expect(existsSync(outbox)).toBe(true)
    const pushed = readFileSync(outbox, "utf8")
    expect(pushed).toContain("【周报】")
    expect(pushed).toContain("完成 1 项")
    expect(pushed).toContain("审批 1 次")

    const again = await runWeeklyDigestTick({
      wiring: app.wiring,
      env: process.env,
      nowMs: () => now,
      config: {
        enabled: true,
        to: "u-owner",
        weekday: shanghai.getUTCDay(),
        hour: shanghai.getUTCHours(),
        minute: shanghai.getUTCMinutes(),
        tickMs: 60_000,
      },
    })
    expect(again).toEqual({ sent: false, reason: "already_sent" })
  })
})
