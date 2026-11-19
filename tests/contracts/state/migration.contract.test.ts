// 锚定契约：空库可初始化到最新 schema 并完成 conversation/message/run 读写；旧 schema 数据经迁移入口升级后关键行仍可读。
import { afterEach, describe, expect, it } from "vitest"
import type { ButlerDb } from "../../../packages/persistence/src/db.js"
import { createRuntimeStore } from "../../../packages/persistence/src/runtime-store.js"
import { makeTestDb } from "../../../packages/persistence/src/testing.js"
import { applyMigrations } from "../../../packages/persistence/src/migrations/run-migrations.js"

const CREATED_AT = new Date("2026-01-01T00:00:00.000Z")

/** 回退到 0002 之后的形状：删掉后续迁移新增的列 / 表，再由 applyMigrations 升级。 */
const DOWNGRADE_TO_PRE_0003 = `
  ALTER TABLE conversations DROP COLUMN IF EXISTS project_id;
  ALTER TABLE scoped_grants DROP COLUMN IF EXISTS delegable;
  ALTER TABLE scoped_grants DROP COLUMN IF EXISTS approval_id;
  ALTER TABLE scoped_grants DROP COLUMN IF EXISTS sandbox_profile;
  ALTER TABLE scoped_grants DROP COLUMN IF EXISTS network_allowlist;
  ALTER TABLE scoped_grants DROP COLUMN IF EXISTS capability;
  ALTER TABLE audit_events DROP COLUMN IF EXISTS correlation_id;
  ALTER TABLE audit_events DROP COLUMN IF EXISTS actor;
  DROP TABLE IF EXISTS durable_memories CASCADE;
  DROP TABLE IF EXISTS documents CASCADE;
  DROP TABLE IF EXISTS procedures CASCADE;
  DROP TABLE IF EXISTS tasks CASCADE;
  DROP TABLE IF EXISTS project_knowledge_items CASCADE;
  DROP TABLE IF EXISTS task_sessions CASCADE;
  DROP TABLE IF EXISTS butler_sessions CASCADE;
`

describe("schema and migration contract", () => {
  let db: Awaited<ReturnType<typeof makeTestDb>> | null = null

  afterEach(async () => {
    await db?.close()
    db = null
  })

  it("initializes an empty database and roundtrips conversation, message and run", async () => {
    db = await makeTestDb()
    const store = createRuntimeStore(db)
    const conversationId = crypto.randomUUID()

    const inbound = await store.createConversationWithUserMessage({
      conversationId,
      messageId: crypto.randomUUID(),
      subject: "owner-contract",
      content: { text: "hello latest schema" },
      triggerSource: "channel",
      idempotencyKey: "latest-msg-key",
      createdAt: CREATED_AT,
    })
    const created = await store.createRun({
      id: crypto.randomUUID(),
      conversationId: inbound.conversationId,
      parentRunId: null,
      triggerSource: "channel",
      idempotencyKey: "latest-run-key",
      subject: "owner-contract",
      goal: "reply",
      budget: { maxSteps: 5 },
      deadline: null,
      createdAt: CREATED_AT,
    })
    const running = await store.transitionRunStatus(
      created.id,
      created.version,
      "running",
      new Date(CREATED_AT.getTime() + 1000),
    )
    await store.transitionRunStatus(
      running.id,
      running.version,
      "succeeded",
      new Date(CREATED_AT.getTime() + 2000),
    )

    const storedRun = await store.getRun(created.id)
    expect(storedRun?.status).toBe("succeeded")
    expect(storedRun?.conversationId).toBe(inbound.conversationId)
    expect(storedRun?.idempotencyKey).toBe("latest-run-key")

    const storedMessages = await store.listMessages(inbound.conversationId)
    expect(storedMessages).toHaveLength(1)
    expect(storedMessages[0]?.id).toBe(inbound.messageId)
    expect(storedMessages[0]?.content).toEqual({ text: "hello latest schema" })
  })

  it("upgrades legacy-shaped data and keeps key rows readable", async () => {
    db = await makeTestDb()
    const activeDb = db
    if (!activeDb) throw new Error("test database was not created")
    await activeDb.pg.exec(DOWNGRADE_TO_PRE_0003)

    const conversationId = "c-legacy-contract"
    const messageId = crypto.randomUUID()
    const runId = crypto.randomUUID()
    await activeDb.pg.query(
      `INSERT INTO conversations (conversation_id, subject, created_at, updated_at)
       VALUES ($1, $2, $3, $4)`,
      [conversationId, "legacy-owner", CREATED_AT, CREATED_AT],
    )
    await activeDb.pg.query(
      `INSERT INTO messages
         (message_id, conversation_id, role, content, trigger_source, idempotency_key, created_at)
       VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)`,
      [
        messageId,
        conversationId,
        "user",
        JSON.stringify({ text: "legacy hello" }),
        "channel",
        "legacy-msg-key",
        CREATED_AT,
      ],
    )
    await activeDb.pg.query(
      `INSERT INTO runs
         (run_id, conversation_id, parent_run_id, trigger_source, idempotency_key, subject,
          goal, status, budget, deadline, version, created_at, updated_at)
       VALUES ($1, $2, NULL, $3, $4, $5, $6, $7, $8::jsonb, NULL, $9, $10, $11)`,
      [
        runId,
        conversationId,
        "channel",
        "legacy-run-key",
        "legacy-owner",
        "reply",
        "succeeded",
        JSON.stringify({ maxSteps: 3 }),
        3,
        CREATED_AT,
        CREATED_AT,
      ],
    )

    await applyMigrations((sql) => activeDb.pg.exec(sql))
    const store = createRuntimeStore(activeDb as unknown as ButlerDb)

    const storedRun = await store.getRun(runId)
    expect(storedRun?.status).toBe("succeeded")
    expect(storedRun?.version).toBe(3)
    expect(storedRun?.idempotencyKey).toBe("legacy-run-key")
    expect(storedRun?.conversationId).toBe(conversationId)

    const storedMessages = await store.listMessages(conversationId)
    expect(storedMessages).toHaveLength(1)
    expect(storedMessages[0]?.id).toBe(messageId)
    expect(storedMessages[0]?.idempotencyKey).toBe("legacy-msg-key")
    expect(storedMessages[0]?.content).toEqual({ text: "legacy hello" })
  })
})
