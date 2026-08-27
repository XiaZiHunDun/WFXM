/**
 * T2: Scheme B dev delegate mock trajectory (wechat-dev-delegate-v1).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import { mkdtempSync, readFileSync, rmSync, existsSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { parsePendingCapabilityInput } from "@butler/runtime/approval-runtime.js"
import { Hono } from "hono"
import { createOwnerRoutes } from "./owner-routes.js"
import { createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { runButlerLoop, type ButlerLoopLogger } from "./wechat-inbound-butler.js"
import { resolveIntakeLoopOptions } from "./wechat-intake.js"
import { runSubagentWorker } from "./subagent-worker.js"
import { normalizeCapabilityNames } from "./capability-guard.js"
import {
  pollMockOutboxForText,
  waitForCondition,
} from "./wechat-async-harness.js"

function textResponse(content: string): LLMAssistantResponse {
  return { content, toolCalls: [], stopReason: "end_turn" }
}

describe("wechat-dev-delegate-v1 (T2)", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  let wiring: Wiring
  let workspaceRoot: string
  let stateStore: string
  let mockOutbox: string
  const fromUserId = "owner-test-delegate-v1"
  const silentLogger: ButlerLoopLogger = {
    warn: () => undefined,
    error: () => undefined,
  }

  beforeEach(async () => {
    workspaceRoot = mkdtempSync(join(tmpdir(), "butler-v5-delegate-ws-"))
    stateStore = join(mkdtempSync(join(tmpdir(), "butler-v5-delegate-st-")), "state.json")
    mockOutbox = join(tmpdir(), `butler-notify-delegate-${Date.now()}.jsonl`)
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-delegate-v1" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-delegate-v1",
      runtimeStore,
      runEngine: new RunEngine(runtimeStore),
      db: db.db,
      backfillConversation: async () => undefined,
    })
  })

  afterEach(async () => {
    vi.restoreAllMocks()
    await db.close()
    rmSync(workspaceRoot, { recursive: true, force: true })
    rmSync(join(stateStore, ".."), { recursive: true, force: true })
    try {
      rmSync(mockOutbox, { force: true })
    } catch {
      // ignore
    }
  })

  function baseEnv(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
    return {
      BUTLER_V5_SUBAGENT_ENABLED: "1",
      BUTLER_V5_DEV_DIRECT_EXEC: "0",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "",
      BUTLER_V5_WORKSPACE_ROOT: workspaceRoot,
      BUTLER_V5_PROJECT_STATE_STORE: stateStore,
      BUTLER_V5_DEV_VERIFY_ENABLED: "1",
      BUTLER_V5_DEV_VERIFY_CMD: '["echo","ok"]',
      BUTLER_V5_RUN_NOTIFY_ENABLED: "1",
      BUTLER_V5_RUN_NOTIFY_MOCK_OUTBOX: mockOutbox,
      ...extra,
    }
  }

  it("plan Loop with scheme B tool surface delegates without write_file@", async () => {
    const env = baseEnv()
    const loopOpts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "write file" },
      projectId: "wechat",
      env,
    })
    expect(loopOpts.allowedToolNames).toContain("delegate_to_subagent")
    expect(loopOpts.allowedToolNames).not.toContain("write_file")

    const adapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(
              JSON.stringify({
                _tag: "Delegate",
                role: "developer",
                task: "write tmp-dev-delegate-v1.txt",
              }),
            ),
          ),
        )
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(JSON.stringify({ _tag: "Respond", content: "已委派开发子代理" })),
          ),
        ),
    } satisfies LLMAdapter

    const result = await runButlerLoop({
      wiring,
      conversationId: "c-dev-delegate-v1",
      content: "帮我写入 tmp-dev-delegate-v1.txt 内容 scheme-b-ok",
      fromUserId,
      projectId: "wechat",
      allowedToolNames: loopOpts.allowedToolNames,
      env,
      logger: silentLogger,
      adapter,
    })

    expect(result.traces.some((t) => t.startsWith("write_file@"))).toBe(false)
    expect(result.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)
    expect(result.reply).toBe("已委派开发子代理")

    const events = await bridge.loadStream("c-dev-delegate-v1")
    expect(events.some((e) => e.eventType === "ChildRunCreated")).toBe(true)
  })

  it("full chain: plan delegate → exec write_file → dev verify → mock outbox", async () => {
    const env = baseEnv()
    const targetFile = "tmp-dev-delegate-v1.txt"

    const planAdapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(
              JSON.stringify({
                _tag: "Delegate",
                role: "developer",
                task: `write ${targetFile} content scheme-b-ok`,
              }),
            ),
          ),
        )
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(JSON.stringify({ _tag: "Respond", content: "已委派，子代理执行中" })),
          ),
        ),
    } satisfies LLMAdapter

    const execAdapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed({
            content: "",
            toolCalls: [
              {
                id: "tc-write-1",
                name: "write_file",
                args: { path: targetFile, content: "scheme-b-ok" },
              },
            ],
            stopReason: "tool_use" as const,
          }),
        )
        .mockImplementationOnce(() =>
          Effect.succeed(textResponse("文件已写入")),
        ),
    } satisfies LLMAdapter

    const conversationId = "c-dev-delegate-full"
    const loopOpts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "write file" },
      projectId: "wechat",
      env,
    })

    const planResult = await runButlerLoop({
      wiring,
      conversationId,
      content: `帮我写入 ${targetFile} 内容 scheme-b-ok`,
      fromUserId,
      projectId: "wechat",
      allowedToolNames: loopOpts.allowedToolNames,
      env,
      logger: silentLogger,
      adapter: planAdapter,
    })
    expect(planResult.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)

    const created = await bridge.loadStream(conversationId)
    const childCreated = created.find((e) => e.eventType === "ChildRunCreated")
    const childCaps = normalizeCapabilityNames(
      (childCreated?.payload as { capabilities?: unknown }).capabilities,
    )
    expect(childCaps).toContain("write_file")

    const workerHandle = runSubagentWorker(
      bridge,
      () => execAdapter,
      env,
      {
        logger: silentLogger,
        intervalMs: 10,
        runtimeStore: wiring.runtimeStore,
      },
    )

    const workerDone = await waitForCondition(async () => {
      const events = await bridge.loadStream(conversationId)
      return events.some(
        (e) =>
          e.eventType === "AssistantMessageProduced" &&
          String((e.payload as { content?: string }).content ?? "").includes("子代理 developer"),
      )
    }, { timeoutMs: 10_000 })
    expect(workerDone).toBe(true)
    workerHandle.stop()

    const writtenPath = join(workspaceRoot, targetFile)
    expect(existsSync(writtenPath)).toBe(true)
    expect(readFileSync(writtenPath, "utf8")).toBe("scheme-b-ok")

    const events = await bridge.loadStream(conversationId)
    const assistant = events.find(
      (e) =>
        e.eventType === "AssistantMessageProduced" &&
        String((e.payload as { content?: string }).content ?? "").includes("子代理 developer"),
    )
    expect(assistant).toBeDefined()
    expect(String((assistant?.payload as { content?: string }).content ?? "")).toContain(
      "【开发验收】",
    )

    const outbox = await pollMockOutboxForText({
      path: mockOutbox,
      includes: "【开发验收】",
      timeoutMs: 15_000,
    })
    expect(outbox.length).toBeGreaterThan(0)
  }, 30_000)

  it("child run_command under P2 allowlist → pending approval → Owner approve → resume", async () => {
    const env = baseEnv({
      BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist",
      BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS: "1",
    })
    const conversationId = "c-dev-approve-egress"

    const planAdapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(
              JSON.stringify({
                _tag: "Delegate",
                role: "developer",
                task: '必须 CallTool run_command argv=["python3","-c","print(888)"]',
              }),
            ),
          ),
        )
        .mockImplementationOnce(() =>
          Effect.succeed(textResponse(JSON.stringify({ _tag: "Respond", content: "已委派子代理执行命令" }))),
        ),
    } satisfies LLMAdapter

    // Child issues run_command once; under P2 allowlist run_command is NOT
    // pre-granted (delegation-grants excludes it), so the capability boundary
    // persists a waiting_approval step (persistAskApproval) instead of running.
    const execAdapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed({
            content: "",
            toolCalls: [
              {
                id: "tc-run-1",
                name: "run_command",
                args: { argv: ["python3", "-c", "print(888)"] },
              },
            ],
            stopReason: "tool_use" as const,
          }),
        )
        .mockImplementationOnce(() => Effect.succeed(textResponse("已执行，输出 888"))),
    } satisfies LLMAdapter

    const loopOpts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "run command" },
      projectId: "wechat",
      env,
    })
    const planResult = await runButlerLoop({
      wiring,
      conversationId,
      content: "帮我运行命令 print(888)",
      fromUserId,
      projectId: "wechat",
      allowedToolNames: loopOpts.allowedToolNames,
      env,
      logger: silentLogger,
      adapter: planAdapter,
    })
    expect(planResult.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)

    const workerHandle = runSubagentWorker(
      bridge,
      () => execAdapter,
      env,
      {
        logger: silentLogger,
        intervalMs: 10,
        runtimeStore: wiring.runtimeStore,
      },
    )

    // The pending run_command approval step is persisted by the real subagent
    // path (subagent-worker → tool-boundary → capability-boundary.persistAskApproval).
    let stepId: string | null = null
    const pendingPosted = await waitForCondition(async () => {
      const steps = await wiring.runtimeStore.listWaitingApprovalSteps()
      const hit = steps.find((s) => {
        const p = parsePendingCapabilityInput(s.input)
        return p?.capability === "run_command"
      })
      if (hit) stepId = hit.id
      return hit !== undefined
    }, { timeoutMs: 15_000, pollIntervalMs: 50 })
    expect(pendingPosted).toBe(true)
    expect(stepId).toBeTruthy()
    workerHandle.stop()

    // Owner approves via the loopback owner-routes API (Scheme B network egress).
    const app = new Hono()
    createOwnerRoutes(app, wiring)
    const res = await app.request(`/v1/owner/approvals/${stepId}/approve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        subject: "owner-1",
        networkAllowlist: ["registry.npmjs.org:443"],
      }),
    })
    const body = (await res.json()) as {
      ok: boolean
      grant?: { sandboxProfile?: string; networkAllowlist?: string[] }
      output?: string
      reason?: string
    }
    expect(res.status).toBe(200)
    expect(body.ok).toBe(true)
    expect(body.grant?.sandboxProfile).toBe("workspace-write-network-allowlist")
    expect(body.grant?.networkAllowlist).toEqual(["registry.npmjs.org:443"])
    // resumeApprovedCapability re-executes run_command under the granted env →
    // deterministic output "888" (sandbox disabled in test, in-process python).
    expect(String(body.output ?? "")).toContain("888")
  }, 30_000)
})
