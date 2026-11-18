import { describe, expect, it } from "vitest"
import type { PiTaskSessionRecord } from "@butler/ports/core/pi-task-session.js"
import { DrizzlePiTaskSessionStore } from "./task-session-store.js"
import { makeTestDb } from "./testing.js"

function record(overrides: Partial<PiTaskSessionRecord> = {}): PiTaskSessionRecord {
  const now = new Date("2026-11-17T00:00:00Z").toISOString()
  return {
    taskId: "task-1",
    projectId: "proj-1",
    cwd: "/tmp/workspace",
    status: "idle",
    snapshot: {
      version: 1,
      systemPrompt: "you are a task agent",
      messages: [{ role: "user", content: "hello", timestamp: 1 }],
    },
    pendingStep: null,
    createdAt: now,
    updatedAt: now,
    ...overrides,
  }
}

describe("DrizzlePiTaskSessionStore", () => {
  it("round-trips a session with a pending approval step", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzlePiTaskSessionStore(db)
      const pendingStep = {
        toolCallId: "call-1",
        toolName: "write",
        args: { path: "a.txt" },
        reason: "需要审批",
        requestedAt: "2026-11-17T00:00:01Z",
      }
      await store.save(record({ status: "paused", pendingStep }))

      const loaded = await store.load("task-1")
      expect(loaded).toEqual(record({ status: "paused", pendingStep }))
    } finally {
      await db.close()
    }
  })

  it("updates, lists by status and deletes", async () => {
    const db = await makeTestDb()
    try {
      const store = new DrizzlePiTaskSessionStore(db)
      await store.save(record())
      await store.save(record({ status: "paused" }))
      await store.save(record({ taskId: "task-2", status: "paused" }))

      const paused = await store.listByStatus("paused")
      expect(paused.map((entry) => entry.taskId).sort()).toEqual(["task-1", "task-2"])

      await store.delete("task-1")
      expect(await store.load("task-1")).toBeNull()
      expect((await store.listByStatus("paused")).map((entry) => entry.taskId)).toEqual(["task-2"])
    } finally {
      await db.close()
    }
  })
})
