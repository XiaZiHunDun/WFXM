/**
 * Acceptance: reminder create → due → outbox push.
 * Uses the scripted LLM fixtures and the mock outbox so it never sends real
 * WeChat messages. Verifies the full chat-tool → store → worker path.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterAll, beforeAll, describe, expect, it } from "vitest"
import { runReminderTick } from "@butler/api/reminder-worker.js"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  textEntry,
  toolCallEntry,
  type AcceptanceApp,
} from "../harness.js"

function shanghaiNowPlus(ms: number): string {
  const d = new Date(Date.now() + ms + 8 * 3600_000)
  return `${d.toISOString().slice(0, 16).replace("T", " ")}`
}

describe("acceptance/reminder (创建 → 到点 → 出站)", () => {
  let app: AcceptanceApp
  let dir: string
  let outbox: string
  const previousEnabled = process.env["BUTLER_V5_REMINDERS_ENABLED"]
  const previousOutbox = process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"]

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "reminder-acceptance-"))
    outbox = join(dir, "outbox.jsonl")
    process.env["BUTLER_V5_REMINDERS_ENABLED"] = "1"
    process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] = outbox
    app = await makeAcceptanceApp()
  })

  afterAll(async () => {
    await app.close()
    rmSync(dir, { recursive: true, force: true })
    if (previousEnabled === undefined) delete process.env["BUTLER_V5_REMINDERS_ENABLED"]
    else process.env["BUTLER_V5_REMINDERS_ENABLED"] = previousEnabled
    if (previousOutbox === undefined) delete process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"]
    else process.env["BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX"] = previousOutbox
  })

  it("creates a reminder and pushes it when due", async () => {
    app.setFixtures({
      plan: [
        toolCallEntry(
          "create_reminder",
          { content: "冒烟提醒", fireAt: shanghaiNowPlus(2 * 60_000) },
          "tc-reminder",
        ),
        textEntry("已设置提醒"),
      ],
    })
    const inbound = await sendWechatMessage(app, { content: "两分钟后提醒我冒烟提醒" })
    expect(inbound.reply).toContain("已设置")

    const store = app.wiring.reminderStore
    if (!store) throw new Error("reminder store missing")
    const rows = await store.listActiveBySubject({ subject: "u-owner" })
    expect(rows).toHaveLength(1)
    const reminder = rows[0]
    if (!reminder) throw new Error("reminder not persisted")

    const stats = await runReminderTick({
      wiring: app.wiring,
      env: process.env,
      nowMs: () => reminder.fireAtMs + 1_000,
    })
    expect(stats).toEqual({ fired: 1, failed: 0 })
    expect(existsSync(outbox)).toBe(true)
    expect(readFileSync(outbox, "utf8")).toContain("【提醒】冒烟提醒")
    expect((await store.get(reminder.id))?.status).toBe("done")
  })
})
