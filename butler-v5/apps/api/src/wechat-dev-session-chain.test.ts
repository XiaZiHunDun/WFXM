/**
 * Loopback: dev session grant → dev_task delegate chain (P1 + working-set).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Effect } from "effect"
import { mkdtempSync, rmSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"
import type { LLMAdapter, LLMAssistantResponse } from "@butler/adapters"
import { buildWechatRunTrigger } from "@butler/domain/runtime.js"
import { EventBridge } from "@butler/persistence/event-bridge.js"
import { RunEngine } from "@butler/runtime/run-engine.js"
import { createRuntimeStore } from "@butler/persistence"
import { makeTestDb } from "@butler/persistence/testing.js"
import { makeWiring, type Wiring } from "./wiring.js"
import { routeWechatIntake, resolveIntakeLoopOptions } from "./wechat-intake.js"
import { devSessionRunId } from "./dev-session-grant.js"
import { runButlerLoop, type ButlerLoopLogger } from "./wechat-inbound-butler.js"

function textResponse(content: string): LLMAssistantResponse {
  return { content, toolCalls: [], stopReason: "end_turn" }
}

describe("wechat dev session chain", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>>
  let bridge: EventBridge
  let wiring: Wiring
  let workspaceRoot: string
  const fromUserId = "owner-dev-session-chain"
  const silentLogger: ButlerLoopLogger = {
    warn: () => undefined,
    error: () => undefined,
  }

  beforeEach(async () => {
    workspaceRoot = mkdtempSync(join(tmpdir(), "butler-v5-dev-chain-ws-"))
    db = await makeTestDb()
    bridge = new EventBridge({ db: db.db, workerId: "w-dev-chain" })
    const runtimeStore = createRuntimeStore(db.db)
    wiring = makeWiring({
      bridge,
      workerId: "w-dev-chain",
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
  })

  function baseEnv(): NodeJS.ProcessEnv {
    return {
      BUTLER_V5_SUBAGENT_ENABLED: "1",
      BUTLER_V5_DEV_DIRECT_EXEC: "0",
      BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH: "",
      BUTLER_V5_WORKSPACE_ROOT: workspaceRoot,
      BUTLER_V5_INTAKE_ENABLED: "1",
      BUTLER_V5_INTAKE_LLM: "0",
    }
  }

  it("dev session → dev_task issues scoped_grants and delegates with dev working-set trace", async () => {
    const env = baseEnv()
    const conversationId = "c-dev-session-chain"

    const sessionResult = await routeWechatIntake({
      wiring,
      conversationId,
      content: "开发模式",
      fromUserId,
      projectId: "wechat",
      env,
    })
    expect(sessionResult.reply).toContain("开发模式")

    const grant = await wiring.runtimeStore.findActiveGrant({
      runId: devSessionRunId(fromUserId),
      subject: fromUserId,
      capability: "run_command",
      now: new Date(),
    })
    expect(grant).not.toBeNull()

    await wiring.runtimeStore.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: fromUserId,
      content: { text: "ping" },
      triggerSource: "channel",
      idempotencyKey: "noise-ping",
      createdAt: new Date(),
    })
    await wiring.runtimeStore.appendMessage({
      messageId: crypto.randomUUID(),
      conversationId,
      role: "assistant",
      content: { text: "pong" },
      triggerSource: "channel",
      idempotencyKey: "noise-pong",
      createdAt: new Date(),
    })

    const loopOpts = resolveIntakeLoopOptions({
      intent: { kind: "dev_task", goal: "write file" },
      projectId: "wechat",
      env,
    })
    const adapter = {
      complete: vi
        .fn()
        .mockImplementationOnce(() =>
          Effect.succeed(
            textResponse(
              JSON.stringify({
                _tag: "Delegate",
                role: "developer",
                task: "write tmp-dev-session-chain.txt",
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

    const devTask = await runButlerLoop({
      wiring,
      conversationId,
      content: "帮我写入 tmp-dev-session-chain.txt",
      fromUserId,
      projectId: "wechat",
      allowedToolNames: loopOpts.allowedToolNames,
      runTrigger: buildWechatRunTrigger({
        userId: fromUserId,
        conversationId,
        content: "帮我写入 tmp-dev-session-chain.txt",
        extraPayload: { workingSetMode: "dev" },
      }),
      env,
      logger: silentLogger,
      adapter,
    })

    expect(devTask.traces.some((t) => t.startsWith("delegate_to_subagent@"))).toBe(true)
    expect(devTask.reply).toContain("委派")

    const events = await bridge.loadStream(conversationId)
    expect(events.some((e) => e.eventType === "ChildRunCreated")).toBe(true)
  })
})
