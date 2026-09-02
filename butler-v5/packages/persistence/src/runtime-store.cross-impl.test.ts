/**
 * RuntimeStore 契约一致性线束（cross-impl，S4 / D47 + parity 补齐）。
 *
 * 证明 Repository Port（`RuntimeStore` 合同，`@butler/domain/runtime/store-contract.js`）
 * 是"可替换单一接缝"：用同一组断言函数对两个实现同时跑：
 *   1. production：createRuntimeStore(makeTestDb())          // Drizzle + PGlite（@butler/persistence/testing）
 *   2. 第二实现  ：createInMemoryRuntimeStore()               // D46，纯内存（memory/runtime-store.ts）
 *
 * 断言二者在以下可观察行为上一致：
 *   - 会话 / 消息（写入、追加、按时间序读取、按 projectId 列举、idempotencyKey 去重）
 *   - Run 状态流转 + 乐观版本冲突（版本递增、过期版本冲突抛错）
 *   - Step CRUD + waiting-approval 列举（kind==='approval' + status==='waiting' 门控、createdAt asc）
 *   - grant 剩余次数与过期（digest 语义、耗尽、按 capability / MCP server 吊销）
 *   - audit 追加 + withTransaction / *InTx 变体的原子组合
 *   - 主 Run 选择（active-main / child createdAt desc / 超 deadline 的 ACTIVE 状态过滤 + deadline asc）
 *
 * 已知 in-memory 简化点（契约以生产实现为准，不强行在生产 store 上削足适履）：
 * 下文 "documented in-memory simplifications" 逐条标注，并在 PR 中上报 S1。
 * S-A（idempotency 去重）/ S-C（waiting-approval 门控）/ S-D（deadline 状态门控）/
 * S-E（child 排序）/ S-F（digest 语义）已由 memory 实现补齐，并在本线束中双向锁定；
 * 仅剩 S-B（content 落库脱敏）为刻意的内存简化（内存非耐久转录）。
 */

import { describe, expect, it } from "vitest"
import type { RuntimeStore, StoredRun } from "@butler/domain/runtime.js"
import { createRuntimeStore } from "./runtime-store.js"
import { createInMemoryRuntimeStore } from "./memory/runtime-store.js"
import { makeTestDb } from "./testing.js"

interface StoreHandle {
  readonly store: RuntimeStore
  readonly close: () => Promise<void>
}
type StoreFactory = () => Promise<StoreHandle>

const productionFactory: StoreFactory = async () => {
  const db = await makeTestDb()
  return { store: createRuntimeStore(db), close: () => db.close() }
}

const memoryFactory: StoreFactory = async () => ({
  store: createInMemoryRuntimeStore(),
  close: async () => {},
})

const BASE_AT = new Date("2026-09-02T00:00:00.000Z")
const t = (ms = 0): Date => new Date(BASE_AT.getTime() + ms)

/** 建会话 + 一条 user 消息 + 一个 Run，返回引用（供两实现共用，避免 FK/差异）。 */
async function seedConversationAndRun(
  store: RuntimeStore,
  projectId = "WFXM",
): Promise<{ readonly conversationId: string; readonly runId: string }> {
  const conversationId = crypto.randomUUID()
  const runId = crypto.randomUUID()
  await store.createConversationWithUserMessage({
    conversationId,
    messageId: crypto.randomUUID(),
    subject: "owner",
    content: { text: "hello" },
    triggerSource: "channel",
    idempotencyKey: `seed-msg-${runId}`,
    createdAt: t(0),
    projectId,
  })
  await store.createRun({
    id: runId,
    conversationId,
    parentRunId: null,
    triggerSource: "channel",
    idempotencyKey: `seed-run-${runId}`,
    subject: "owner",
    goal: "reply",
    budget: { maxSteps: 5 },
    deadline: null,
    createdAt: t(0),
  })
  return { conversationId, runId }
}

/** 对两个实现跑同一组"契约一致"断言。 */
function paritySuite(name: string, make: StoreFactory): void {
  describe(`RuntimeStore 契约一致性线束 — ${name}`, () => {
    async function using<T>(fn: (store: RuntimeStore) => Promise<T>): Promise<T> {
      const h = await make()
      try {
        return await fn(h.store)
      } finally {
        await h.close()
      }
    }

    it("会话 + 消息：写入、追加、按时间序读取、按 projectId 列举", async () => {
      await using(async (store) => {
        const cid = crypto.randomUUID()
        const created = await store.createConversationWithUserMessage({
          conversationId: cid,
          messageId: crypto.randomUUID(),
          subject: "owner",
          content: { text: "hello" },
          triggerSource: "channel",
          idempotencyKey: "ik-conv-1",
          createdAt: t(0),
          projectId: "WFXM",
        })
        expect(created).toEqual({ conversationId: cid, messageId: created.messageId })

        const appended = await store.appendMessage({
          messageId: crypto.randomUUID(),
          conversationId: cid,
          role: "assistant",
          content: { text: "hi" },
          triggerSource: null,
          idempotencyKey: null,
          createdAt: t(1000),
        })
        expect(appended.role).toBe("assistant")

        expect((await store.listMessages(cid)).map((m) => m.role)).toEqual([
          "user",
          "assistant",
        ])

        const convs = await store.listConversationsByProject({ projectId: "WFXM" })
        const match = convs.find((c) => c.id === cid)
        expect(match?.projectId).toBe("WFXM")
      })
    })

    it("Run 状态流转 + 乐观版本冲突：版本递增，过期版本冲突抛错", async () => {
      await using(async (store) => {
        const { runId } = await seedConversationAndRun(store)
        expect((await store.getRun(runId))?.status).toBe("queued")
        expect((await store.getRun(runId))?.version).toBe(1)

        const running = await store.transitionRunStatus(runId, 1, "running", t(1000))
        expect(running).toMatchObject({ status: "running", version: 2 })

        await expect(
          store.transitionRunStatus(runId, 1, "failed", t(2000)),
        ).rejects.toThrow(/version/i)

        const current = await store.getRun(runId)
        expect(current?.status).toBe("running")
        expect(current?.version).toBe(2)
      })
    })

    it("主 Run 选择：active-main / child run / 超 deadline 的 active run", async () => {
      await using(async (store) => {
        const { runId, conversationId: cid } = await seedConversationAndRun(store)
        await store.transitionRunStatus(runId, 1, "running", t(1000))

        expect((await store.findActiveMainRun(cid))?.id).toBe(runId)

        const childId = crypto.randomUUID()
        await store.createRun({
          id: childId,
          conversationId: cid,
          parentRunId: runId,
          triggerSource: "parent_run",
          idempotencyKey: `child-${childId}`,
          subject: "owner",
          goal: "child",
          budget: {},
          deadline: t(5000),
          createdAt: t(2000),
        })
        expect((await store.findChildRuns(runId)).map((r) => r.id)).toEqual([childId])
        expect((await store.listRunsPastDeadline(t(6000))).map((r) => r.id)).toEqual([
          childId,
        ])
      })
    })

    it("Step CRUD + waiting-approval 按 conversation 列举（approval kind 对齐输入）", async () => {
      await using(async (store) => {
        const { runId, conversationId: cid } = await seedConversationAndRun(store)
        const stepId = crypto.randomUUID()
        const step = await store.createStep({
          id: stepId,
          runId,
          kind: "approval",
          status: "waiting",
          input: { question: "ok?" },
          createdAt: t(0),
        })
        expect(step.output).toBeNull()

        const updated = await store.updateStep({
          stepId,
          status: "succeeded",
          output: { ok: true },
          updatedAt: t(1000),
        })
        expect(updated).toMatchObject({ status: "succeeded", output: { ok: true } })

        const stillId = crypto.randomUUID()
        await store.createStep({
          id: stillId,
          runId,
          kind: "approval",
          status: "waiting",
          input: {},
          createdAt: t(3000),
        })
        expect((await store.listWaitingApprovalSteps()).map((s) => s.id)).toEqual([
          stillId,
        ])
        expect(
          (await store.listWaitingApprovalStepsForConversation(cid)).map((s) => s.id),
        ).toEqual([stillId])
      })
    })

    it("grant 剩余次数与过期：digest 匹配、耗尽为 null、按 capability/MCP 吊销", async () => {
      await using(async (store) => {
        const { runId } = await seedConversationAndRun(store)
        const t0 = t(0)
        const grantId = crypto.randomUUID()
        const base = { runId, subject: "owner", capability: "read_file" }
        await store.createScopedGrant({
          grantId,
          runId,
          subject: "owner",
          capability: "read_file",
          scope: { digest: "d1" },
          remainingUses: 2,
          expiresAt: t(60_000),
          createdAt: t0,
        })
        expect(
          (await store.findActiveGrant({ ...base, digest: "d1", now: t0 }))?.remainingUses,
        ).toBe(2)
        expect(await store.findActiveGrant({ ...base, digest: "other", now: t0 })).toBeNull()
        expect(
          await store.findActiveGrant({ ...base, digest: "d1", now: t(60_001) }),
        ).toBeNull()

        await store.updateScopedGrantRemainingUses(grantId, 0)
        expect(await store.findActiveGrant({ ...base, digest: "d1", now: t0 })).toBeNull()

        await store.createScopedGrant({
          grantId: crypto.randomUUID(),
          runId,
          subject: "owner",
          capability: "write_file",
          scope: { digest: "d2" },
          remainingUses: 1,
          expiresAt: t(60_000),
          createdAt: t0,
        })
        expect(await store.revokeScopedGrantsForCapability("write_file", t0)).toBe(1)
        expect(
          await store.findActiveGrant({
            ...base,
            capability: "write_file",
            digest: "d2",
            now: t0,
          }),
        ).toBeNull()

        await store.createScopedGrant({
          grantId: crypto.randomUUID(),
          runId,
          subject: "owner",
          capability: "mcp.server.tool",
          scope: { mcp: { serverId: "srvA", toolName: "search" } },
          remainingUses: 1,
          expiresAt: t(60_000),
          createdAt: t0,
        })
        expect(await store.countActiveScopedGrantsForMcpServer("srvA", t0)).toBe(1)
        expect(await store.revokeScopedGrantsForMcpServer("srvA", t0)).toBe(1)
        expect(await store.countActiveScopedGrantsForMcpServer("srvA", t0)).toBe(0)
      })
    })

    it("audit 追加 + withTransaction / *InTx 变体原子组合", async () => {
      await using(async (store) => {
        const { runId } = await seedConversationAndRun(store)
        await store.appendAuditEvent({
          auditId: crypto.randomUUID(),
          runId,
          conversationId: null,
          action: "test",
          subject: "owner",
          detail: { k: 1 },
          createdAt: t(0),
        })
        const ran = await store.withTransaction(async (tx) => {
          await store.appendAuditEventInTx(tx, {
            auditId: crypto.randomUUID(),
            runId: null,
            conversationId: null,
            action: "tx-test",
            subject: "owner",
            detail: {},
            createdAt: t(1000),
          })
          return store.transitionRunStatusInTx(tx, runId, 1, "running", t(1000))
        })
        expect(ran.status).toBe("running")
        expect((await store.getRun(runId))?.version).toBe(2)
      })
    })

    it("idempotency：createRun / createConversationWithUserMessage / appendMessage 按 idempotencyKey 返回既有记录（S-A）", async () => {
      await using(async (store) => {
        const { runId } = await seedConversationAndRun(store)
        const existing = (await store.getRun(runId)) as StoredRun
        const again = await store.createRun({
          id: crypto.randomUUID(),
          conversationId: existing.conversationId,
          parentRunId: null,
          triggerSource: "channel",
          idempotencyKey: existing.idempotencyKey,
          subject: "owner",
          goal: "reply",
          budget: {},
          deadline: null,
          createdAt: t(0),
        })
        expect(again.id).toBe(runId)

        const cid = crypto.randomUUID()
        const first = await store.createConversationWithUserMessage({
          conversationId: cid,
          messageId: crypto.randomUUID(),
          subject: "owner",
          content: { text: "hello" },
          triggerSource: "channel",
          idempotencyKey: "replay-conv-1",
          createdAt: t(0),
          projectId: "WFXM",
        })
        const replay = await store.createConversationWithUserMessage({
          conversationId: cid,
          messageId: crypto.randomUUID(),
          subject: "owner",
          content: { text: "hello again" },
          triggerSource: "channel",
          idempotencyKey: "replay-conv-1",
          createdAt: t(1000),
        })
        expect(replay).toEqual(first)
        expect(
          (await store.listConversationsByProject({ projectId: "WFXM" })).filter(
            (c) => c.id === cid,
          ),
        ).toHaveLength(1)

        const appended = await store.appendMessage({
          messageId: crypto.randomUUID(),
          conversationId: cid,
          role: "assistant",
          content: { text: "reply" },
          triggerSource: null,
          idempotencyKey: "replay-append-1",
          createdAt: t(2000),
        })
        const appendedAgain = await store.appendMessage({
          messageId: crypto.randomUUID(),
          conversationId: cid,
          role: "assistant",
          content: { text: "reply again" },
          triggerSource: null,
          idempotencyKey: "replay-append-1",
          createdAt: t(3000),
        })
        expect(appendedAgain.id).toBe(appended.id)
        expect((await store.listMessages(cid)).map((m) => m.role)).toEqual([
          "user",
          "assistant",
        ])
      })
    })

    it("waiting-approval：仅 kind==='approval' 且 status==='waiting' 命中，按 createdAt asc（S-C）", async () => {
      await using(async (store) => {
        const { runId, conversationId: cid } = await seedConversationAndRun(store)
        const approvalEarly = crypto.randomUUID()
        await store.createStep({
          id: approvalEarly,
          runId,
          kind: "approval",
          status: "waiting",
          input: {},
          createdAt: t(1000),
        })
        await store.createStep({
          id: crypto.randomUUID(),
          runId,
          kind: "model",
          status: "waiting",
          input: {},
          createdAt: t(1500),
        })
        await store.createStep({
          id: crypto.randomUUID(),
          runId,
          kind: "approval",
          status: "succeeded",
          input: {},
          createdAt: t(2000),
        })
        const approvalLate = crypto.randomUUID()
        await store.createStep({
          id: approvalLate,
          runId,
          kind: "approval",
          status: "waiting",
          input: {},
          createdAt: t(3000),
        })
        const expected = [approvalEarly, approvalLate]
        expect((await store.listWaitingApprovalSteps()).map((s) => s.id)).toEqual(expected)
        expect(
          (await store.listWaitingApprovalStepsForConversation(cid)).map((s) => s.id),
        ).toEqual(expected)
      })
    })

    it("listRunsPastDeadline：仅 ACTIVE_MAIN_RUN_STATUSES 的过期 run，按 deadline asc（S-D）", async () => {
      await using(async (store) => {
        const { runId, conversationId: cid } = await seedConversationAndRun(store)
        const terminalId = crypto.randomUUID()
        await store.createRun({
          id: terminalId,
          conversationId: cid,
          parentRunId: runId,
          triggerSource: "parent_run",
          idempotencyKey: `term-${terminalId}`,
          subject: "owner",
          goal: "g",
          budget: {},
          deadline: t(500),
          createdAt: t(1000),
        })
        await store.transitionRunStatus(terminalId, 1, "failed", t(1500))

        const earlyId = crypto.randomUUID()
        const lateId = crypto.randomUUID()
        for (const [id, deadline, createdAt] of [
          [earlyId, t(1000), t(2000)],
          [lateId, t(3000), t(3000)],
        ] as const) {
          await store.createRun({
            id,
            conversationId: cid,
            parentRunId: runId,
            triggerSource: "parent_run",
            idempotencyKey: `act-${id}`,
            subject: "owner",
            goal: "g",
            budget: {},
            deadline,
            createdAt,
          })
        }

        const listed = await store.listRunsPastDeadline(t(6000))
        expect(listed.map((r) => r.id)).toEqual([earlyId, lateId])
        expect(listed.some((r) => r.id === terminalId)).toBe(false)
      })
    })

    it("findChildRuns：按 createdAt desc（最近在先）（S-E）", async () => {
      await using(async (store) => {
        const { runId, conversationId: cid } = await seedConversationAndRun(store)
        const early = crypto.randomUUID()
        const late = crypto.randomUUID()
        for (const [id, at] of [
          [early, t(1000)],
          [late, t(3000)],
        ] as const) {
          await store.createRun({
            id,
            conversationId: cid,
            parentRunId: runId,
            triggerSource: "parent_run",
            idempotencyKey: `child-${id}`,
            subject: "owner",
            goal: "g",
            budget: {},
            deadline: null,
            createdAt: at,
          })
        }
        expect((await store.findChildRuns(runId)).map((r) => r.id)).toEqual([late, early])
      })
    })

    it("findActiveGrant digest：无 scope.digest 的 grant 接受任意 digest；固定 digest 须精确匹配（S-F）", async () => {
      await using(async (store) => {
        const { runId } = await seedConversationAndRun(store)
        await store.createScopedGrant({
          grantId: crypto.randomUUID(),
          runId,
          subject: "owner",
          capability: "read_file",
          scope: {},
          remainingUses: 1,
          expiresAt: t(60_000),
          createdAt: t(0),
        })
        expect(
          await store.findActiveGrant({
            runId,
            subject: "owner",
            capability: "read_file",
            digest: "anything",
            now: t(0),
          }),
        ).not.toBeNull()

        await store.createScopedGrant({
          grantId: crypto.randomUUID(),
          runId,
          subject: "owner",
          capability: "write_file",
          scope: { digest: "d1" },
          remainingUses: 1,
          expiresAt: t(60_000),
          createdAt: t(0),
        })
        expect(
          await store.findActiveGrant({
            runId,
            subject: "owner",
            capability: "write_file",
            digest: "other",
            now: t(0),
          }),
        ).toBeNull()
        expect(
          await store.findActiveGrant({
            runId,
            subject: "owner",
            capability: "write_file",
            digest: "d1",
            now: t(0),
          }),
        ).not.toBeNull()
      })
    })
  })
}

paritySuite("production (Drizzle + PGlite)", productionFactory)
paritySuite("in-memory (D46 second implementation)", memoryFactory)

/**
 * 已知 in-memory 简化点。契约以生产实现为准：这些断言只 pin 生产行为，
 * 记录 in-memory 在相应可观察面上的差异（不作为对本线束的失败项），供 S1 收口。
 * 差异点汇总也写入 PR 描述。
 */
describe("documented in-memory simplifications (契约以生产为准)", () => {
  it("S-B content redaction：生产在落库前对消息内容脱敏；in-memory 存原始内容", async () => {
    const db = await makeTestDb()
    const store = createRuntimeStore(db)
    try {
      const cid = crypto.randomUUID()
      await store.createConversationWithUserMessage({
        conversationId: cid,
        messageId: crypto.randomUUID(),
        subject: "owner",
        content: { text: "token=deadbeef" },
        triggerSource: "channel",
        idempotencyKey: "redact-1",
        createdAt: t(0),
      })
      const stored = (await store.listMessages(cid))[0]
      expect(String((stored.content as Record<string, unknown>)["text"])).not.toContain(
        "deadbeef",
      )
      // in-memory 简化：原样存 input.content（脱敏属持久化耐久侧关切，测试/隔离用途可接受）。
    } finally {
      await db.close()
    }
  })
})
