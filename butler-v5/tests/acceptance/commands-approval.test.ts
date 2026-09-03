/**
 * 微信消息模拟验收 — 核心命令 + 审批流。
 *
 * 脚本化 LLM(fixture) 驱动真实 `/v1/wechat/inbound`，不调真模型/真微信/真服务。
 * 覆盖：/记住 命令捷径（LLM-free）、普通回复（Respond）、写文件审批往返
 * （CallCapability write_file → policy Ask → waiting_approval → 微信「确认」
 * 恢复执行 → run 达终态）。
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

describe("acceptance/commands-approval (微信核心命令 + 审批流)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })
  afterAll(async () => {
    await app.close()
  })

  it("/记住 命令捷径在 LLM-free 下返回「已记住」", async () => {
    app.setFixtures({ plan: [] })
    const res = await sendWechatMessage(app, { content: "/记住 accept: butler 验收标记" })
    expect(res.status).toBe(201)
    expect(res.reply).toContain("已记住")
  }, 30_000)

  it("脚本化 LLM 以文本 Respond 返回普通答复", async () => {
    app.setFixtures({ plan: [textResponse("我已收到，稍后处理。")] })
    const res = await sendWechatMessage(app, { content: "帮我处理一下这件事" })
    expect(res.status).toBe(201)
    expect(res.reply).toContain("我已收到")
    expect(res.finalDecision).toBe("Respond")
  }, 30_000)

  it("write_file 触发审批（policy Ask → waiting_approval），微信「确认」后恢复执行并达终态", async () => {
    app.setFixtures({
      plan: [
        toolCallEntry("write_file", {
          path: "notes.txt",
          content: "hello from acceptance",
        }),
      ],
    })
    const first = await sendWechatMessage(app, {
      content: "帮我写个文件 notes.txt 内容是 hello from acceptance",
    })
    expect(first.status).toBe(201)
    // policy 门控：不静默执行、不自动发 grant，回复含审批提示
    expect(first.reply).toMatch(/需要确认|审批编号|approve/i)
    expect(first.finalDecision).toBe("WaitForApproval")
    expect(first.conversationId).toBeTypeOf("string")

    // 审批恢复走真实行内审批处理（tryWechatInlineApproval）
    const approved = await sendWechatMessage(app, {
      content: "确认",
      conversationId: first.conversationId,
    })
    expect(approved.status).toBe(201)
    expect(approved.reply).toBeTypeOf("string")
    expect(approved.reply).not.toContain("没有待审批")

    // run 达终态
    expect(first.conversationId).toBeDefined()
    const convId = first.conversationId as string
    const runRows = await app.db.select().from(runs).where(eq(runs.conversationId, convId))
    expect(runRows.length).toBeGreaterThan(0)
    const run = runRows[runRows.length - 1]
    expect(run).toBeDefined()
    expect(run?.status).toBe("succeeded")
  }, 30_000)
})

function textResponse(content: string) {
  return { content, toolCalls: [], stopReason: "end_turn" as const }
}