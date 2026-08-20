import { getTableName } from "drizzle-orm"
import { describe, expect, it } from "vitest"
import { auditEvents, conversations, messages, runs, scopedGrants, steps } from "./schema.js"
import { makeTestDb } from "./testing.js"

describe("target runtime migration and schema", () => {
  it("exports every target runtime table", () => {
    expect(
      [conversations, messages, runs, steps, scopedGrants, auditEvents].map(getTableName),
    ).toEqual(["conversations", "messages", "runs", "steps", "scoped_grants", "audit_events"])
  })

  it("applies the target runtime migration to test databases", async () => {
    const db = await makeTestDb()
    try {
      const result = await db.pg.query<{ table_name: string }>(`
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN (
            'conversations', 'messages', 'runs', 'steps', 'scoped_grants', 'audit_events'
          )
        ORDER BY table_name
      `)
      expect(result.rows.map((row) => row.table_name)).toEqual([
        "audit_events",
        "conversations",
        "messages",
        "runs",
        "scoped_grants",
        "steps",
      ])
    } finally {
      await db.close()
    }
  })

  it("enforces inbound idempotency and one active main Run per conversation", async () => {
    const db = await makeTestDb()
    const conversationId = crypto.randomUUID()
    try {
      await db.pg.exec(`
        INSERT INTO conversations (conversation_id, subject, created_at, updated_at)
        VALUES ('${conversationId}', 'owner-1', now(), now());
        INSERT INTO messages (
          message_id, conversation_id, role, content, trigger_source, idempotency_key, created_at
        ) VALUES (
          '${crypto.randomUUID()}', '${conversationId}', 'user', '{"text":"one"}',
          'channel', 'same-key', now()
        );
      `)
      await expect(
        db.pg.exec(`
          INSERT INTO messages (
            message_id, conversation_id, role, content, trigger_source, idempotency_key, created_at
          ) VALUES (
            '${crypto.randomUUID()}', '${conversationId}', 'user', '{"text":"two"}',
            'channel', 'same-key', now()
          );
        `),
      ).rejects.toThrow()

      await db.pg.exec(`
        INSERT INTO runs (
          run_id, conversation_id, parent_run_id, trigger_source, idempotency_key,
          subject, goal, status, budget, deadline, version, created_at, updated_at
        ) VALUES (
          '${crypto.randomUUID()}', '${conversationId}', NULL, 'channel', 'run-key-1',
          'owner-1', 'first', 'queued', '{"maxSteps":5}', NULL, 1, now(), now()
        );
      `)
      await expect(
        db.pg.exec(`
          INSERT INTO runs (
            run_id, conversation_id, parent_run_id, trigger_source, idempotency_key,
            subject, goal, status, budget, deadline, version, created_at, updated_at
          ) VALUES (
            '${crypto.randomUUID()}', '${conversationId}', NULL, 'channel', 'run-key-2',
            'owner-1', 'second', 'running', '{"maxSteps":5}', NULL, 1, now(), now()
          );
        `),
      ).rejects.toThrow()
    } finally {
      await db.close()
    }
  })
})
