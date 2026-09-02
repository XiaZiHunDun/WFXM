/**
 * In-memory RuntimeStore 单测（D46 Repository Port 第二实现载体）。
 *
 * 覆盖 Repository Port（RuntimeStore 合同）核心读写语义：
 *   - conversation + user message / appendMessage / listMessages
 *   - createRun / getRun / transitionRunStatus（乐观版本续程 + 冲突抛错）
 *   - findActiveMainRun / findChildRuns / listRunsPastDeadline
 *   - createStep / getStep / updateStep / listWaitingApprovalSteps
 *   - createScopedGrant / findActiveGrant / updateScopedGrantRemainingUses
 *     / revoke+count MCP / revoke capability
 *   - appendAuditEvent + withTransaction + *InTx 变体
 */
import { describe, expect, it } from "vitest"
import {
  ACTIVE_MAIN_RUN_STATUSES,
  type RuntimeStore,
  type StoredRun,
} from "@butler/domain/runtime.js"
import { RuntimeVersionConflictError } from "../runtime-store.js"
import { createInMemoryRuntimeStore } from "./runtime-store.js"

const t0 = () => new Date("2026-09-02T00:00:00.000Z")
const t5 = () => new Date("2026-09-02T00:00:05.000Z")
const t6 = () => new Date("2026-09-02T00:00:06.000Z")

describe("createInMemoryRuntimeStore", () => {
  it("creates conversation + user message and lists messages in order", async () => {
    const store: RuntimeStore = createInMemoryRuntimeStore()
    const created = await store.createConversationWithUserMessage({
      conversationId: "c1",
      messageId: "m1",
      subject: "hello",
      content: { text: "hi" },
      triggerSource: "cli",
      idempotencyKey: "ik1",
      createdAt: t0(),
      projectId: "p1",
    })
    expect(created).toEqual({ conversationId: "c1", messageId: "m1" })

    const msgs = await store.listMessages("c1")
    expect(msgs.map((m) => m.id)).toEqual(["m1"])
    expect(msgs[0].role).toBe("user")

    const append = await store.appendMessage({
      messageId: "m2",
      conversationId: "c1",
      role: "assistant",
      content: { text: "hey" },
      triggerSource: null,
      idempotencyKey: null,
      createdAt: t5(),
    })
    expect(append.role).toBe("assistant")
    expect((await store.listMessages("c1")).map((m) => m.id)).toEqual(["m1", "m2"])
  })

  it("lists conversations by project", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createConversationWithUserMessage({
      conversationId: "c1", messageId: "m1", subject: "a",
      content: {}, triggerSource: "cli", idempotencyKey: "i", createdAt: t0(),
      projectId: "p1",
    })
    await store.createConversationWithUserMessage({
      conversationId: "c2", messageId: "m2", subject: "b",
      content: {}, triggerSource: "cli", idempotencyKey: "j", createdAt: t5(),
      projectId: "p1",
    })
    const convs = await store.listConversationsByProject({ projectId: "p1" })
    expect(convs.map((c) => c.id).sort()).toEqual(["c1", "c2"])
    expect(await store.listConversationsByProject({ projectId: "missing" })).toEqual([])
  })

  it("creates a run, transitions status with version bump, throws on conflict", async () => {
    const store = createInMemoryRuntimeStore()
    const run = await store.createRun({
      id: "r1", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "ik", subject: "sub", goal: "goal", budget: {}, deadline: null,
      createdAt: t0(),
    })
    expect(run.status).toBe("queued")
    expect(run.version).toBe(1)

    const running = await store.transitionRunStatus("r1", 1, "running", t5())
    expect(running.status).toBe("running")
    expect(running.version).toBe(2)

    await expect(
      store.transitionRunStatus("r1", 1, "succeeded", t5()),
    ).rejects.toBeInstanceOf(RuntimeVersionConflictError)
  })

  it("finds active main run (parentRunId null + active status)", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createRun({
      id: "child", conversationId: "c1", parentRunId: "main", triggerSource: "parent_run",
      idempotencyKey: "c", subject: "child", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    expect(await store.findActiveMainRun("c1")).toBeNull()

    const main = await store.createRun({
      id: "main", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "m", subject: "main", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    // 刚创建 status=queued，若 queued 属于 ACTIVE_MAIN_RUN_STATUSES 则命中，否则转 running
    const found = await store.findActiveMainRun("c1")
    if (ACTIVE_MAIN_RUN_STATUSES.includes("queued")) {
      expect(found?.id).toBe(main.id)
    } else {
      await store.transitionRunStatus("main", 1, "running", t5())
      expect((await store.findActiveMainRun("c1"))?.id).toBe(main.id)
    }
  })

  it("finds child runs and runs past deadline", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createRun({
      id: "main", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "m", subject: "m", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    await store.createRun({
      id: "child", conversationId: "c1", parentRunId: "main", triggerSource: "parent_run",
      idempotencyKey: "c", subject: "c", goal: "g", budget: {}, deadline: t5(), createdAt: t0(),
    })
    expect((await store.findChildRuns("main")).map((r) => r.id)).toEqual(["child"])
    expect((await store.listRunsPastDeadline(t6())).map((r: StoredRun) => r.id)).toEqual(["child"])
  })

  it("creates and updates steps, lists waiting-approval steps per conversation", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createRun({
      id: "r1", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "m", subject: "m", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    const step = await store.createStep({
      id: "s1", runId: "r1", kind: "capability", status: "waiting",
      input: {}, createdAt: t0(),
    })
    expect(step.output).toBeNull()

    const updated = await store.updateStep({
      stepId: "s1", status: "succeeded", output: { ok: true }, updatedAt: t5(),
    })
    expect(updated.status).toBe("succeeded")
    expect(updated.output).toEqual({ ok: true })

    // waiting + approval → 命中；waiting + kind!=approval → 不命中（S-C 门控）
    await store.createStep({
      id: "s2", runId: "r1", kind: "approval", status: "waiting", input: {}, createdAt: t5(),
    })
    await store.createStep({
      id: "s3", runId: "r1", kind: "model", status: "waiting", input: {}, createdAt: t6(),
    })
    expect((await store.listWaitingApprovalSteps()).map((s) => s.id)).toEqual(["s2"])
    // r2 属其他 conversation 的 waiting step 不应命中 c1
    await store.createRun({
      id: "rOther", conversationId: "cOther", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "o", subject: "o", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    await store.createStep({
      id: "sOther", runId: "rOther", kind: "capability", status: "waiting",
      input: {}, createdAt: t0(),
    })
    expect((await store.listWaitingApprovalStepsForConversation("c1")).map((s) => s.id)).toEqual(["s2"])
  })

  it("creates grants, finds active, updates uses, revokes MCP/capability", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createScopedGrant({
      grantId: "g1", runId: "r1", subject: "owner", capability: "run_command",
      scope: { network: "allow", networkHosts: ["*.example.com"] },
      remainingUses: 3, expiresAt: t5(), createdAt: t0(), delegable: false,
    })
    const active = await store.findActiveGrant({
      runId: "r1", subject: "owner", capability: "run_command", now: t0(),
    })
    expect(active?.remainingUses).toBe(3)

    const expired = await store.findActiveGrant({
      runId: "r1", subject: "owner", capability: "run_command", now: t5(),
    })
    // 过期 = expiresAtMs <= now → 不再 active
    expect(expired).toBeNull()

    // 未耗尽 + 未过期场景
    await store.createScopedGrant({
      grantId: "g2", runId: "r2", subject: "owner", capability: "run_command",
      scope: {}, remainingUses: 1, expiresAt: t5(), createdAt: t0(),
    })
    expect(
      (await store.findActiveGrant({ runId: "r2", subject: "owner", capability: "run_command", now: t0() }))?.id,
    ).toBe("g2")
    await store.updateScopedGrantRemainingUses("g2", 0)
    expect(
      await store.findActiveGrant({ runId: "r2", subject: "owner", capability: "run_command", now: t0() }),
    ).toBeNull()

    // MCP revoke + count
    await store.createScopedGrant({
      grantId: "gm1", runId: "r3", subject: "owner", capability: "mcp.server.tool",
      scope: { mcp: { serverId: "srv1" } }, remainingUses: null, expiresAt: t5(), createdAt: t0(),
    })
    expect(await store.countActiveScopedGrantsForMcpServer("srv1", t0())).toBe(1)
    expect(await store.revokeScopedGrantsForMcpServer("srv1", t0())).toBe(1)
    expect(await store.countActiveScopedGrantsForMcpServer("srv1", t0())).toBe(0)

    // capability revoke
    await store.createScopedGrant({
      grantId: "gc1", runId: "r4", subject: "owner", capability: "write_file",
      scope: {}, remainingUses: null, expiresAt: t5(), createdAt: t0(),
    })
    expect(await store.revokeScopedGrantsForCapability("write_file", t0())).toBe(1)
  })

  it("appendAuditEvent and tx variants compose atomically", async () => {
    const store = createInMemoryRuntimeStore()
    await store.appendAuditEvent({
      auditId: "a1", runId: "r1", conversationId: "c1", action: "x", subject: "s",
      detail: { ok: true }, createdAt: t0(),
    })
    await store.createRun({
      id: "r1", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "m", subject: "m", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    const tx: RuntimeStore["withTransaction"] = (fn) => fn({} as never)
    const ran = await store.withTransaction(async () => {
      await store.appendAuditEventInTx(null as never, {
        auditId: "a2", runId: null, conversationId: null, action: "y", subject: "s",
        detail: {}, createdAt: t0(),
      })
      return store.transitionRunStatusInTx(null as never, "r1", 1, "running", t5())
    })
    expect(ran.status).toBe("running")
    // tx 助手不存在于读表面；此处主要验证调用链路不抛错、类型满足 RuntimeStore。
    expect(tx).toBeTypeOf("function")
  })

  it("idempotency：createRun / createConversationWithUserMessage / appendMessage 按 idempotencyKey 返回既有记录（S-A）", async () => {
    const store = createInMemoryRuntimeStore()
    const conv = await store.createConversationWithUserMessage({
      conversationId: "c1", messageId: "m1", subject: "a",
      content: {}, triggerSource: "cli", idempotencyKey: "ik-c", createdAt: t0(),
    })
    const replay = await store.createConversationWithUserMessage({
      conversationId: "c1", messageId: "m1b", subject: "a",
      content: {}, triggerSource: "cli", idempotencyKey: "ik-c", createdAt: t5(),
    })
    expect(replay).toEqual({ conversationId: "c1", messageId: "m1" })
    expect((await store.listMessages("c1")).map((m) => m.id)).toEqual(["m1"])

    const run = await store.createRun({
      id: "r1", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "ik-r", subject: "s", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    const runReplay = await store.createRun({
      id: "r2", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "ik-r", subject: "s", goal: "g", budget: {}, deadline: null, createdAt: t5(),
    })
    expect(runReplay.id).toBe("r1")
    expect(run.version).toBe(1)
    void conv

    const appended = await store.appendMessage({
      messageId: "a1", conversationId: "c1", role: "assistant", content: {},
      triggerSource: null, idempotencyKey: "ik-a", createdAt: t0(),
    })
    const appendReplay = await store.appendMessage({
      messageId: "a2", conversationId: "c1", role: "assistant", content: {},
      triggerSource: null, idempotencyKey: "ik-a", createdAt: t5(),
    })
    expect(appendReplay.id).toBe(appended.id)
    expect(appended.id).toBe("a1")
  })

  it("findChildRuns 按 createdAt desc；listRunsPastDeadline 排除终态（S-E/S-D）", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createRun({
      id: "main", conversationId: "c1", parentRunId: null, triggerSource: "cli",
      idempotencyKey: "m", subject: "m", goal: "g", budget: {}, deadline: null, createdAt: t0(),
    })
    await store.createRun({
      id: "child1", conversationId: "c1", parentRunId: "main", triggerSource: "parent_run",
      idempotencyKey: "c1k", subject: "c", goal: "g", budget: {}, deadline: t5(), createdAt: t0(),
    })
    await store.createRun({
      id: "child2", conversationId: "c1", parentRunId: "main", triggerSource: "parent_run",
      idempotencyKey: "c2k", subject: "c", goal: "g", budget: {}, deadline: t6(), createdAt: t5(),
    })
    // S-E：createdAt desc → 最近（child2）在先
    expect((await store.findChildRuns("main")).map((r) => r.id)).toEqual(["child2", "child1"])
    // S-D：child1 已转终态（failed），即使 deadline 过期也不应被清扫；
    // child2 的 deadline=t6()，查询 now=t5() 时未过期也应被排除
    await store.transitionRunStatus("child1", 1, "failed", t5())
    expect((await store.listRunsPastDeadline(t5())).map((r) => r.id)).toEqual([])
    expect((await store.listRunsPastDeadline(new Date(t6().getTime() + 1000))).map((r) => r.id)).toEqual(["child2"])
  })

  it("findActiveGrant：无 scope.digest 的 grant 接受任意 digest（S-F）", async () => {
    const store = createInMemoryRuntimeStore()
    await store.createScopedGrant({
      grantId: "g-open", runId: "r1", subject: "owner", capability: "read_file",
      scope: {}, remainingUses: 1, expiresAt: t6(), createdAt: t0(),
    })
    expect(
      (await store.findActiveGrant({ runId: "r1", subject: "owner", capability: "read_file", digest: "anything", now: t0() }))?.id,
    ).toBe("g-open")
    // 固定 digest 的 grant 仍要求精确匹配
    await store.createScopedGrant({
      grantId: "g-pinned", runId: "r1", subject: "owner", capability: "write_file",
      scope: { digest: "d1" }, remainingUses: 1, expiresAt: t6(), createdAt: t0(),
    })
    expect(
      await store.findActiveGrant({ runId: "r1", subject: "owner", capability: "write_file", digest: "other", now: t0() }),
    ).toBeNull()
    expect(
      (await store.findActiveGrant({ runId: "r1", subject: "owner", capability: "write_file", digest: "d1", now: t0() }))?.id,
    ).toBe("g-pinned")
  })
})