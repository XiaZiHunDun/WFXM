/**
 * 微信消息模拟验收 — 产品层回归锁（/undo 命令 + 垃圾消息护栏 + LLM 遥测 +
 * inline-approval intents + run_command read-only bypass + pnpm install 审批）。
 *
 * 脚本化 LLM(fixture) 驱动真实 `/v1/wechat/inbound`，不调真模型/真微信/真服务。
 *
 * 覆盖以下产品层真实修复的回归锁：
 *   1. `/undo <path>`：真实审批恢复 + undoLastWrite 还原内容。预先在工作区
 *      创建 `undo.txt=before`，fixture write_file 写 `after`，走完审批往返
 *      后 `/undo undo.txt` 必须还原文件内容，并回复 `已还原`。
 *   2. 垃圾消息护栏：发 `"请".repeat(80)`（单字符重复 80 次）必须被
 *      `detectSpam` 短路，回复命中 `消息过长|重复|具体需求`，且不消耗 LLM
 *      fixture（toolCalls=0，不含 fixture marker `SHOULD_NOT_BE_USED`）。
 *   3. LLM 遥测：跑通一次普通对话后，本地 tracer 必须记录到至少一条
 *      `kind=step, name=llm_call` 事件，且所有匹配事件的 status 为 `ok`，
 *      证明 §14 observability 的 llm_call 埋点没有断流。
 *   4. inline-approval intents：owner 用 `y` / `👌` / `✅` / `👍` 任一 intent
 *      token，应能 resume waiting approval step 并完成 write_file 实际写入。
 *   5. run_command read-only argv（`ls`）：d226f33f owner bypass 命中，
 *      finalDecision 不能是 WaitForApproval。
 *   6. run_command write argv（`pnpm install`）：不在 isReadOnlyCommand 白名单，
 *      finalDecision 必须是 WaitForApproval。
 *
 * 每个用例独立 conversationId，避免 ActiveMainRunConflict 跨用例污染。
 */
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { afterAll, beforeAll, describe, expect, it } from "vitest"
import { resetSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  textEntry,
  toolCallEntry,
  type AcceptanceApp,
} from "./harness.js"

describe("acceptance/product-regressions (微信产品层回归：/undo + 垃圾护栏)", () => {
  let app: AcceptanceApp

  beforeAll(async () => {
    app = await makeAcceptanceApp()
  })

  afterAll(async () => {
    await app.close()
  })

  it("/undo：真实审批后还原 write_file 写入", async () => {
    // 1. 预先在工作区根写入 `before`，让后续 write_file 的「pre-write content」
    //    栈帧能 pop 出 "before"。/undo 走 tryWechatUndoCommand → undoLastWrite
    //    → writeFileSync 写回。
    const undoPath = "undo.txt"
    const undoFile = join(app.workspaceRoot, undoPath)
    writeFileSync(undoFile, "before", "utf8")

    // 2. 单条 write_file fixture：写 `after`，期望触发 policy Ask →
    //    WaitForApproval（run paused）。
    app.setFixtures({
      plan: [toolCallEntry("write_file", { path: undoPath, content: "after" })],
    })

    const convId = "c-product-undo-regression"
    const first = await sendWechatMessage(app, {
      content: "帮我把 undo.txt 改成 after",
      conversationId: convId,
    })
    expect(first.status).toBe(201)
    expect(first.finalDecision).toBe("WaitForApproval")
    expect(first.conversationId).toBe(convId)

    // 3. 真实行内审批：`确认` 复用 waiting step → run 恢复 → write_file 实际
    //    执行（同时把 "before" 压栈 → 弹出 → 写入 "after"）。此时磁盘上
    //    undo.txt 应为 "after"。
    const approved = await sendWechatMessage(app, {
      content: "确认",
      conversationId: convId,
    })
    expect(approved.status).toBe(201)
    expect(approved.reply).toBeTypeOf("string")
    expect(approved.reply).not.toContain("没有待审批")
    expect(readFileSync(undoFile, "utf8")).toBe("after")

    // 4. /undo 命令：tryWechatUndoCommand 命中 → undoLastWrite 弹出 "before"
    //    → writeFileSync 还原。
    const undoRes = await sendWechatMessage(app, {
      content: `/undo ${undoPath}`,
      conversationId: convId,
    })
    expect(undoRes.status).toBe(201)
    expect(undoRes.reply).toContain("已还原")
    expect(readFileSync(undoFile, "utf8")).toBe("before")
  }, 30_000)

  it("垃圾消息护栏（spam guard）：`请`.repeat(80) 短路 LLM，命中重复字符提示", async () => {
    // fixture marker：若护栏失效让 LLM 跑了一次，回复里就会出现这条文案；
    // 用例断言 `not.toContain("SHOULD_NOT_BE_USED")` 即可证明 fixture 未被
    // 消费、护栏短路有效。
    app.setFixtures({
      plan: [textEntry("SHOULD_NOT_BE_USED fixture reply")],
    })

    // "请".repeat(80) = 80 个相同 CJK 字符（maxCount=80 > 30 && 占比=1.0 ≥ 0.3），
    // 命中 detectSpam 的"重复字符"分支：`检测到字符「请」重复 80
    // 次。请发具体需求。`
    const res = await sendWechatMessage(app, {
      content: "请".repeat(80),
      conversationId: "c-product-spam-guard-regression",
    })
    expect(res.status).toBe(201)
    expect(res.reply).toMatch(/消息过长|重复|具体需求/)
    expect(res.toolCalls).toBe(0)
    expect(res.reply).not.toContain("SHOULD_NOT_BE_USED")
  }, 30_000)

  it("LLM 遥测（llm_call tracer）：普通对话产生 step/llm_call 且 status=ok", async () => {
    // 独立 conversationId 隔离前两个用例的 waiting_approval / spam short
    // circuit 状态污染。resetSharedLocalTracer 在用例入口重置 process-wide
    // tracer，注入 BUTLER_V5_TRACE=1 强制开启（默认已开启，显式更稳）。
    const convId = "c-product-llm-telemetry-regression"
    app.setFixtures({
      plan: [textEntry("telemetry reply")],
    })
    const tracer = resetSharedLocalTracer({
      ...process.env,
      BUTLER_V5_TRACE: "1",
      // 强制关闭 OTEL stdout exporter：若父环境开了 stdout，本用例会向
      // stderr 喷 OTLP JSON 行污染 acceptance 输出；显式 pin off 保持
      // 验收日志确定性。
      BUTLER_V5_OTEL_EXPORTER: "off",
    })

    // 普通 inbound → runButlerLoop → executeInbound → plan LLM 调用一次，
    // wechat-inbound-butler.ts 的 Effect.match onSuccess 分支会
    // tracer.record({ kind: "step", name: "llm_call", status: "ok", ... })
    const res = await sendWechatMessage(app, {
      content: "随便打个招呼测遥测",
      conversationId: convId,
    })
    expect(res.status).toBe(201)
    expect(res.reply).toContain("telemetry reply")
    expect(res.conversationId).toBe(convId)

    // 用返回的 conversationId 过滤 tracer：至少一条 step/llm_call 事件，
    // 且所有匹配事件的 status 都是 ok。fixture 不携带 usage，故不验证
    // `token` 字段（D23 §14 observability 留口，legacy fixture 可 null）。
    const events = tracer.list({ conversationId: convId })
    const llmCalls = events.filter(
      (event) => event.kind === "step" && event.name === "llm_call",
    )
    expect(llmCalls.length).toBeGreaterThan(0)
    expect(llmCalls.every((event) => event.status === "ok")).toBe(true)
  }, 30_000)

  describe("inline-approval: single-char/emoji intents drive real resume", () => {
    // P0 回归锁：parseInlineApprovalIntent 识别 `y` / `👌` / `✅` / `👍` 四个
    // intent token（inline-approval-intent.ts L13-17），但单元测试只覆盖
    // intent 解析层；这里把同一组 token 接进 wechat-inbound-butler 的
    // tryWechatInlineApproval → createWaitingApprovalStep resume → write_file
    // 实际执行全链路，确保 owner 在真实 wechat 流上用单字符/emoji 触发
    // 审批放行后，文件真的被改写（不只是 intent 字符串匹配）。
    //
    // 每个 intent 用独立的 conversationId + 文件路径，避免跨用例 waiting
    // approval / 创建态污染；helper 复用 4 次，断言保持显式以让失败信息
    // 直接指向断掉的 intent。

    function itOwnsFileWithApproval(token: string, filePath: string, convId: string): void {
      it(`inline-approval: '${token}' triggers write_file resume end-to-end`, async () => {
        const fullPath = join(app.workspaceRoot, filePath)
        writeFileSync(fullPath, "before", "utf8")
        app.setFixtures({
          plan: [toolCallEntry("write_file", { path: filePath, content: "after" })],
        })

        // 1. Owner 请求写入 → policy Ask → WaitForApproval（run paused）
        const first = await sendWechatMessage(app, {
          content: `把 ${filePath} 改成 after`,
          conversationId: convId,
        })
        expect(first.status).toBe(201)
        expect(first.finalDecision).toBe("WaitForApproval")
        expect(first.conversationId).toBe(convId)

        // 2. Owner 用单字符/emoji intent 应答 → intent 识别为 approve →
        //    复用 waiting step → run 恢复 → write_file 实际写入 "after"。
        //    关键回归点：reply 不能是 "没有待审批"（说明 intent 真被接住），
        //    且磁盘文件必须真的是 "after"（说明执行路径走完）。
        const approved = await sendWechatMessage(app, {
          content: token,
          conversationId: convId,
        })
        expect(approved.status).toBe(201)
        expect(approved.reply).not.toContain("没有待审批")
        expect(readFileSync(fullPath, "utf8")).toBe("after")
      }, 30_000)
    }

    itOwnsFileWithApproval("y", "inline-y.txt", "c-inline-approval-y")
    itOwnsFileWithApproval("👌", "inline-ok.txt", "c-inline-approval-ok")
    itOwnsFileWithApproval("✅", "inline-check.txt", "c-inline-approval-check")
    itOwnsFileWithApproval("👍", "inline-thumbs.txt", "c-inline-approval-thumbs")
  })

  it("run_command read-only argv (`ls`): 不触发审批，finish", async () => {
    // read-only → policy Allow → run actually executes (sandboxed ls is OK)
    app.setFixtures({
      plan: [toolCallEntry("run_command", { argv: ["ls"] })],
    })
    const res = await sendWechatMessage(app, {
      content: "列一下当前目录",
      conversationId: "c-run-command-readonly-ls",
    })
    expect(res.status).toBe(201)
    // 不是 WaitForApproval：read-only argv 跳过 approval
    expect(res.finalDecision).not.toBe("WaitForApproval")
  }, 30_000)

  it("run_command write argv (`pnpm install`): 仍触发审批", async () => {
    // pnpm install 是写操作（修改 node_modules / lockfile），不在
    // isReadOnlyCommand 白名单（仅 typecheck/test），d226f33f 的 owner
    // read-only bypass 不命中，必须走 WaitForApproval。
    app.setFixtures({
      plan: [toolCallEntry("run_command", { argv: ["pnpm", "install"] })],
    })
    const res = await sendWechatMessage(app, {
      content: "安装依赖",
      conversationId: "c-run-command-write-pnpm-install",
    })
    expect(res.status).toBe(201)
    expect(res.finalDecision).toBe("WaitForApproval")
  }, 30_000)
})
