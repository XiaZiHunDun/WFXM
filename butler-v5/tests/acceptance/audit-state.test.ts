/**
 * 微信消息模拟验收 — 审计 + 状态。
 *
 * 覆盖：事件流（event_store）写入、审批授予（scoped_grants）记录、跨"重启"
 * 恢复（同一 PGlite data dir 重开 harness，重放同一 conversationId 的
 * 「确认」→ pending approval 仍可恢复）。
 */
import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { eq } from "drizzle-orm"
import {
  eventStore,
  scopedGrants,
} from "@butler/persistence/schema.js"
import { mkdtempSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  toolCallEntry,
  type AcceptanceApp,
} from "./harness.js"

describe("acceptance/audit-state (微信审计 + 跨重启恢复)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })
  afterAll(async () => {
    await app.close()
  })

  it("入站 → eventStore 写入 ConversationStarted 行（事件流不断）", async () => {
    app.setFixtures({
      plan: [toolCallEntry("write_file", { path: "audit.txt", content: "audit" })],
    })
    const res = await sendWechatMessage(app, {
      content: "帮我写 audit.txt 内容是 audit",
      conversationId: "c-audit-event-store",
    })
    expect(res.status).toBe(201)
    expect(res.conversationId).toBeTypeOf("string")

    const streamId = res.conversationId as string
    const rows = await app.db
      .select()
      .from(eventStore)
      .where(eq(eventStore.streamId, streamId))
    expect(rows.length).toBeGreaterThan(0)
    // 至少一条 ConversationStarted 事件
    const started = rows.filter((r) => r.eventType === "ConversationStarted")
    expect(started.length).toBeGreaterThan(0)
    // 全部事件都带 correlationId 与 actor（事件流 schema 不变量）
    for (const r of rows) {
      expect(r.correlationId).toBeTypeOf("string")
      expect(r.actorKind).toBeTypeOf("string")
      expect(r.actorId).toBeTypeOf("string")
    }
  }, 30_000)

  it("write_file 审批通过后 scoped_grants 表写入 grant 行（capability 审计可追溯）", async () => {
    app.setFixtures({
      plan: [
        toolCallEntry("write_file", { path: "grant-audit.txt", content: "x" }),
      ],
    })
    const first = await sendWechatMessage(app, {
      content: "帮我写 grant-audit.txt 内容是 x",
      conversationId: "c-audit-grants",
    })
    expect(first.finalDecision).toBe("WaitForApproval")

    const second = await sendWechatMessage(app, {
      content: "确认",
      conversationId: first.conversationId,
    })
    expect(second.status).toBe(201)

    // 审批后应该至少有一条 scoped_grants 记录写入（capability 授予的审计可追溯）
    const grantRows = await app.db
      .select()
      .from(scopedGrants)
    expect(grantRows.length).toBeGreaterThan(0)
  }, 30_000)

  it("跨「重启」：close harness → 同 PGlite data dir 重开 → pending approval 仍可恢复", async () => {
    // 共享 PGlite dir，模拟"进程崩溃后重新启动"。每个用例独立 conversationId
    // 避免跨用例 ActiveMainRunConflict 状态污染。
    const sharedDir = mkdtempSync(join(tmpdir(), "wb-accept-restart-"))

    const appA = await makeAcceptanceApp({ pgliteDataDir: sharedDir })
    try {
      appA.setFixtures({
        plan: [
          toolCallEntry("write_file", {
            path: "restart.txt",
            content: "survive restart",
          }),
        ],
      })
      const first = await sendWechatMessage(appA, {
        content: "帮我写 restart.txt",
        conversationId: "c-audit-restart",
      })
      expect(first.status).toBe(201)
      expect(first.finalDecision).toBe("WaitForApproval")
      expect(first.conversationId).toBeTypeOf("string")
      const convId = first.conversationId as string

      // 模拟「重启」：close A → 新建 B 同 data dir
      await appA.close()

      const appB = await makeAcceptanceApp({ pgliteDataDir: sharedDir })
      try {
        // 审批流由 tryWechatInlineApproval 拦截，不走到 LLM；保险起见也 set 一下
        appB.setFixtures({ plan: [] })

        const approved = await sendWechatMessage(appB, {
          content: "确认",
          conversationId: convId,
        })
        expect(approved.status).toBe(201)
        // 真实行内审批：pending step 仍在 step 表里 → 恢复执行 → 终态
        expect(approved.reply).toBeTypeOf("string")
        expect(approved.reply).not.toContain("没有待审批")
        expect(approved.reply).not.toContain("当前对话没有")
      } finally {
        await appB.close()
      }
    } finally {
      try {
        // eslint-disable-next-line no-restricted-imports -- 测试 cleanup
        const { rmSync } = await import("node:fs")
        rmSync(sharedDir, { recursive: true, force: true })
      } catch {
        // ignore cleanup failure
      }
    }
  }, 60_000)
})