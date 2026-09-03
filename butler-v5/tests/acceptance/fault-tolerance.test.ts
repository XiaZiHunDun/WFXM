/**
 * 微信消息模拟验收 — 容错 / 降级路径。
 *
 * 覆盖：入站校验失败不返 500、ActiveMainRunConflict 降级回复、fixture 耗尽降级。
 * 全部基于真实 /v1/wechat/inbound + 脚本化 LLM fixture。
 */
import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { eq } from "drizzle-orm"
import { runs } from "@butler/persistence/schema.js"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  toolCallEntry,
  type AcceptanceApp,
} from "./harness.js"

describe("acceptance/fault-tolerance (微信容错 / 降级路径)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })
  afterAll(async () => {
    await app.close()
  })

  it("入站校验失败（缺 apiVersion）返回 400 文本而非 500/丢消息", async () => {
    // 故意违反 schema：缺 apiVersion，确保 /v1/wechat/inbound 的 c.req.json()
    // 路径走校验分支。Hono 4xx/5xx 行为差异可被显式断言。
    const res = await app.request("/v1/wechat/inbound", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fromUserId: "u-owner", content: "hi" }),
    })
    expect(res.status).toBe(400)
    const text = await res.text()
    expect(text).toContain("invalid body")
  }, 30_000)

  it("同 conversationId 上 run 处于 waiting_approval 时再次入站降级为「未完成审批」回复（ActiveMainRunConflict）", async () => {
    // turn 1: 触发 write_file → policy Ask → waiting_approval（run 仍 active）
    app.setFixtures({
      plan: [toolCallEntry("write_file", { path: "race.txt", content: "first" })],
    })
    const first = await sendWechatMessage(app, {
      content: "帮我写 race.txt",
    })
    expect(first.status).toBe(201)
    expect(first.finalDecision).toBe("WaitForApproval")
    expect(first.conversationId).toBeTypeOf("string")

    const convId = first.conversationId as string

    // turn 2: 同一 conversationId，非「确认」语义 → runButlerLoop 走 executeInbound
    // 命中 ActiveMainRunConflict，runButlerLoop catch 分支返回降级 reply
    // 而非 500 / 丢消息。
    const second = await sendWechatMessage(app, {
      content: "忽略审批，再帮我做点别的",
      conversationId: convId,
    })
    expect(second.status).toBe(201)
    expect(second.reply).toMatch(/未完成|进行中|稍后|未处理/)
    expect(second.reply).not.toContain("ReferenceError")
    expect(second.reply).not.toContain("TypeError")

    // run 仍处于 active 状态（waiting_approval），未丢失也未崩
    const runRows = await app.db.select().from(runs).where(eq(runs.conversationId, convId))
    const lastRun = runRows[runRows.length - 1]
    expect(lastRun).toBeDefined()
    expect(["waiting_approval", "running"]).toContain(lastRun?.status ?? "")
  }, 30_000)

  it("fixture 耗尽时 LLM 返回降级文本（不抛 500）", async () => {
    // plan 列表为空 → 第 N 次调用会走 fixture 兜底（[fixture exhausted: plan#N]）。
    // 用独立 conversationId 隔离 test #2 的 waiting_approval run（默认 conversationId
    // 由 fromUserId+projectId 推导稳定，跨用例会撞 ActiveMainRunConflict）。
    app.setFixtures({ plan: [] })
    const res = await sendWechatMessage(app, {
      content: "fixture 应该被耗尽",
      conversationId: "c-fixture-exhausted-isolation",
    })
    expect(res.status).toBe(201)
    expect(res.reply).toContain("[fixture exhausted: plan#")
    // 不应是 500/HTML 错误页
    expect(res.text).not.toMatch(/<html/i)
    expect(res.text).not.toContain("Internal Server Error")
  }, 30_000)
})