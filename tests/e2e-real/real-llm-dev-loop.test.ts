/**
 * 真实 LLM 开发闭环回归 — 写文件 → 审批 → 运行。
 *
 * 与 `tests/e2e-demo`（脚本化 fixture）互补：本文件走 production wiring +
 * 真实模型，覆盖「模型决定工具调用 → 审批门控 → 沙箱执行 → 结果回流」。
 *
 * 默认跳过，避免 `pnpm test` 联网烧钱。显式开启：
 *
 *   pnpm test:e2e:real
 *
 * 需要 `.env` 里可用的模型 key（DEEPSEEK_API_KEY 等）。
 * 断言只锚定外部可观察结果：审批决策、写入内容、命令输出。
 */
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { afterAll, beforeAll, describe, expect, test } from "vitest"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  type AcceptanceApp,
  type InboundResult,
} from "../acceptance/harness.js"

const ENABLED = process.env["BUTLER_V5_REAL_LLM_E2E"] === "1"

if (ENABLED) {
  try {
    process.loadEnvFile(join(process.cwd(), ".env"))
  } catch {
    // 没有 .env 时交给下方 key 检测跳过。
  }
}

const HAS_KEY = Boolean(
  process.env["DEEPSEEK_API_KEY"] ??
  process.env["MINIMAX_API_KEY"] ??
  process.env["MINIMAX_CN_API_KEY"] ??
  process.env["ANTHROPIC_API_KEY"],
)

const describeReal = ENABLED && HAS_KEY ? describe : describe.skip

describeReal("真实 LLM 开发闭环", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    // noFixture：不注入脚本化 LLM，走 pickLLMForRole 的真实模型分支。
    app = await makeAcceptanceApp({ noFixture: true })
  }, 240_000)

  afterAll(async () => {
    await app.close()
  })

  /** 等待审批则回「确认」，返回最终一轮结果。 */
  async function confirmIfWaiting(first: InboundResult): Promise<InboundResult> {
    if (first.finalDecision !== "WaitForApproval") return first
    return sendWechatMessage(app, {
      content: "确认",
      ...(first.conversationId !== undefined ? { conversationId: first.conversationId } : {}),
    })
  }

  test("write_file：模型发起写文件，审批后才落盘", { timeout: 240_000 }, async () => {
    const target = join(app.workspaceRoot, "real-llm-check.txt")
    const first = await sendWechatMessage(app, {
      content:
        "请直接用 write_file 工具在当前工作区根目录创建文件，路径写 real-llm-check.txt，" +
        "内容只有一行：wfxm-real-llm-ok。不要创建其他文件，不要追问，写完后用一句话汇报。",
    })
    expect(first.status).toBeLessThan(300)
    // 写入属于副作用操作，必须进入审批。
    expect(first.finalDecision, first.reply ?? first.text).toBe("WaitForApproval")
    expect(existsSync(target)).toBe(false)

    const done = await confirmIfWaiting(first)
    expect(done.status).toBeLessThan(300)
    // 批准后的回执既可能是「已批准并执行该步」，也可能直接是工具输出。
    expect(done.reply ?? "").toMatch(/已批准|文件已写入/)
    expect(existsSync(target)).toBe(true)
    expect(readFileSync(target, "utf8")).toContain("wfxm-real-llm-ok")
  })

  test("run_command：模型发起执行，审批后输出回流", { timeout: 240_000 }, async () => {
    const first = await sendWechatMessage(app, {
      content:
        "请直接用 run_command 执行 node -e \"console.log('wfxm-run-ok')\"，" +
        "然后把命令输出原样贴给我。不要做别的事。",
    })
    expect(first.status).toBeLessThan(300)
    expect(first.finalDecision, first.reply ?? first.text).toBe("WaitForApproval")

    const done = await confirmIfWaiting(first)
    expect(done.status).toBeLessThan(300)
    expect(done.reply ?? "").toMatch(/已批准|命令已执行/)
    expect(done.reply ?? "").toContain("wfxm-run-ok")
  })
})
