/**
 * 验收：真实 intake 路径下的「开发任务 → 委派子代理 → 子代理写文件」闭环。
 *
 * 背景：真机微信走 `routeWechatIntake`（分类 → dev_task → delegate_to_subagent），
 * 而旧 harness 无条件关闭 intake，导致这条链路从未被自动化覆盖。这里用脚本化
 * LLM fixture 驱动真实 HTTP 路由 + 真实 outbox worker，覆盖：
 *
 *   1. 默认开关：dev_task 自动建 dev-session 批量授权，子代理 write_file 免逐项审批；
 *   2. 关闭 `BUTLER_V5_DEV_SESSION_AUTO_GRANT` + `BUTLER_V5_DELEGATION_PREGRANT`：
 *      子代理 write_file 进入 waiting_approval，父会话回「确认」后落盘。
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { pickLLMForRole } from "@butler/adapters"
import { devSessionRunId } from "../../apps/api/src/dev-session-grant.js"
import { runSubagentWorker, type SubagentWorkerHandle } from "../../apps/api/src/subagent-worker.js"
import {
  decisionEntry,
  makeAcceptanceApp,
  sendWechatMessage,
  toolCallEntry,
  type AcceptanceApp,
} from "./harness.js"

const OWNER = "u-owner"
const TARGET = "child-note.txt"
const CONTENT = "child-ok"

const DEV_TASK = `帮我写个文件 ${TARGET}，内容是 ${CONTENT}`

const planFixtures = [
  toolCallEntry(
    "delegate_to_subagent",
    { task: `创建 ${TARGET}，内容为 ${CONTENT}`, role: "exec" },
    "tc-delegate-dev",
  ),
  decisionEntry({ _tag: "Respond", content: "已委派子代理处理。" }),
]

const execFixtures = [
  toolCallEntry("write_file", { path: TARGET, content: CONTENT }, "tc-child-write"),
  decisionEntry({ _tag: "Respond", content: `已写入 ${TARGET}` }),
]

const silentLogger = { warn: () => undefined, error: () => undefined }

async function waitFor<T>(fn: () => Promise<T | undefined>, timeoutMs = 8000): Promise<T> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const value = await fn()
    if (value !== undefined) return value
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
  throw new Error(`waitFor timeout after ${timeoutMs}ms`)
}

describe("acceptance/dev-delegate-approval (intake 委派 + 子代理审批)", () => {
  let app: AcceptanceApp | undefined
  let worker: SubagentWorkerHandle | undefined
  const auditDirs: string[] = []

  afterEach(async () => {
    worker?.stop()
    worker = undefined
    await app?.close()
    app = undefined
    while (auditDirs.length > 0) {
      const dir = auditDirs.pop()
      if (dir) rmSync(dir, { recursive: true, force: true })
    }
  })

  async function start(extra: Readonly<Record<string, string>> = {}): Promise<AcceptanceApp> {
    // F31/F35 delegation dedupe reads the subagent audit log: give each app its
    // own file so repeated runs with the same task text are not blocked.
    const auditDir = mkdtempSync(join(tmpdir(), "wb-accept-audit-"))
    auditDirs.push(auditDir)
    const next = await makeAcceptanceApp({
      intake: true,
      overrides: {
        BUTLER_V5_SUBAGENT_ENABLED: "1",
        BUTLER_V5_INTAKE_LLM: "0",
        BUTLER_V5_SUBAGENT_AUDIT_PATH: join(auditDir, "subagent.jsonl"),
        ...extra,
      },
    })
    next.setFixtures({ plan: planFixtures, exec: execFixtures })
    worker = runSubagentWorker(
      next.wiring.eventBridge,
      (env) => pickLLMForRole(env, "exec"),
      process.env,
      { runtimeStore: next.wiring.runtimeStore, intervalMs: 20, logger: silentLogger },
    )
    app = next
    return next
  }

  it("默认开关：dev_task 自动建批量授权，子代理写文件免逐项审批", async () => {
    const current = await start()
    const res = await sendWechatMessage(current, { content: DEV_TASK })
    expect(res.status).toBe(201)
    expect(res.reply).toContain("已委派")

    const grant = await current.wiring.runtimeStore.findActiveGrant({
      runId: devSessionRunId(OWNER),
      subject: OWNER,
      capability: "write_file",
      now: new Date(),
    })
    expect(grant).not.toBeNull()

    const target = join(current.workspaceRoot, TARGET)
    await waitFor(async () => (existsSync(target) ? true : undefined))
    expect(readFileSync(target, "utf8")).toContain(CONTENT)
  }, 30_000)

  it("关闭两层自动授权：出现子代理待审批，父会话「确认」后落盘", async () => {
    const current = await start({
      BUTLER_V5_DEV_SESSION_AUTO_GRANT: "0",
      BUTLER_V5_DELEGATION_PREGRANT: "0",
    })
    const first = await sendWechatMessage(current, { content: DEV_TASK })
    expect(first.status).toBe(201)
    expect(first.conversationId).toBeTypeOf("string")
    const convId = first.conversationId as string

    const grant = await current.wiring.runtimeStore.findActiveGrant({
      runId: devSessionRunId(OWNER),
      subject: OWNER,
      capability: "write_file",
      now: new Date(),
    })
    expect(grant).toBeNull()

    const step = await waitFor(async () => {
      const steps = await current.wiring.runtimeStore.listWaitingApprovalSteps()
      return steps.find((candidate) => {
        const raw = (candidate.input as { readonly conversationId?: unknown }).conversationId
        return typeof raw === "string" && raw.startsWith(`child-${convId}-`)
      })
    })
    expect(step).toBeDefined()

    const target = join(current.workspaceRoot, TARGET)
    expect(existsSync(target)).toBe(false)

    const second = await sendWechatMessage(current, { content: "确认", conversationId: convId })
    expect(second.status).toBe(201)
    expect(second.reply ?? "").not.toContain("没有待审批")
    await waitFor(async () => (existsSync(target) ? true : undefined))
    expect(readFileSync(target, "utf8")).toContain(CONTENT)
  }, 30_000)
})
