/**
 * D70 T1 (audit #11 SO-005): HTTP surface tests for owner audit-fatigue
 * endpoints. The previous D69 ship had 0 HTTP-level tests — only unit
 * tests at the replay-fatigue-sequence function level (replay-api.test.ts).
 * Now that buildHonoApp mounts owner routes (acceptance-app.ts), this
 * file closes SO-005 by exercising the actual HTTP boundary: route
 * registration, owner auth short-circuit (loopback-or-VITEST), request
 * validation, JSON shape of the response.
 *
 * The undo dispatcher is honest about its scope: write_file/edit_file
 * without audit-event detail → `failed` with owner-jargon reason. We
 * assert that `replayed` stays empty for events that cannot actually be
 * undone — the CQ-010 silent-no-op regression cannot return here
 * because the dispatcher returns ok:false on missing path detail.
 */
import { describe, test, expect, vi } from "vitest"
import { Hono } from "hono"
import { registerAuditFatigueRoutes } from "./audit-fatigue.js"
import type { Wiring } from "../wiring.js"
import type { RuntimeStore, AuditEventRecord } from "@butler/domain/runtime.js"

function makeMockRuntimeStore(events: readonly AuditEventRecord[] = []): RuntimeStore {
  return {
    listRecentAuditEvents: vi.fn(async () => events),
    appendAuditEvent: vi.fn(async () => undefined),
  } as unknown as RuntimeStore
}

function makeWiring(runtimeStore: RuntimeStore): Wiring {
  // Only the fields consumed by registerAuditFatigueRoutes + the type
  // contract. ownerAuthorized reads (env, no socket) → VITEST gate
  // returns true when the test runner sets VITEST=1 (vitest does).
  return {
    runtimeStore,
    eventBridge: {} as Wiring["eventBridge"],
    workerId: "test-worker",
    version: "v5",
    runEngine: {} as Wiring["runEngine"],
    db: {} as Wiring["db"],
    backfillConversation: async () => undefined,
    mcp: {} as Wiring["mcp"],
    durableMemoryStore: null,
    documentStore: null,
    projectKnowledgeStore: null,
    procedureStore: null,
    taskStore: null,
    channels: new Map(),
  }
}

function makeHonoWithAuditFatigue(wiring: Wiring): Hono {
  const app = new Hono()
  registerAuditFatigueRoutes(app, wiring)
  return app
}

describe("/v1/owner/audit/fatigue — HTTP surface (D70 T1 SO-005)", () => {
  test("GET returns empty sequences when audit log is empty", async () => {
    const wiring = makeWiring(makeMockRuntimeStore([]))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue")
    expect(res.status).toBe(200)
    const body = (await res.json()) as { sequences: unknown[]; degraded?: true }
    expect(body.sequences).toEqual([])
    expect(body.degraded).toBeUndefined()
  })

  test("GET accepts window_seconds query param", async () => {
    const wiring = makeWiring(makeMockRuntimeStore([]))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue?window_seconds=120")
    expect(res.status).toBe(200)
    expect((await res.json())).toMatchObject({ sequences: [] })
  })

  test("GET falls back to 60s window when query param is invalid", async () => {
    const wiring = makeWiring(makeMockRuntimeStore([]))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue?window_seconds=-5")
    expect(res.status).toBe(200)
    expect((await res.json())).toMatchObject({ sequences: [] })
  })

  test("POST rejects non-object body", async () => {
    const wiring = makeWiring(makeMockRuntimeStore([]))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue/replay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "null",
    })
    expect(res.status).toBe(400)
    const body = (await res.json()) as { error: string }
    expect(body.error).toMatch(/请求体格式错误|invalid body/)
  })

  test("POST rejects missing sequence_event_ids", async () => {
    const wiring = makeWiring(makeMockRuntimeStore([]))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue/replay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })

  test("POST returns replayed=[] and failed=[...] for reversible events without audit-event detail (CQ-010 honesty)", async () => {
    // The CQ-010 silent-no-op fix: when audit-event detail is missing the
    // path/workspaceRoot, the dispatcher returns ok:false and the event
    // lands in `failed`, NOT `replayed`. Owner sees an honest answer.
    const now = new Date()
    const events: readonly AuditEventRecord[] = [
      {
        auditId: "evt-write-1",
        runId: null,
        conversationId: null,
        // D72 T1: actor column now read via columnActor=true; fixtures
        // must mirror production default 'owner' (appendAuditEvent falls
        // back to 'owner' when actor is not threaded).
        actor: "owner",
        action: "fatigue.decision",
        subject: "write_file", // tool name per audit-reader mapping
        detail: {}, // missing path + workspaceRoot — D71+ infrastructure work
        createdAt: now,
        correlationId: null,
      },
    ]
    const wiring = makeWiring(makeMockRuntimeStore(events))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue/replay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sequence_event_ids: ["evt-write-1"] }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      replayed: string[]
      irreversible: string[]
      failed: { event_id: string; reason: string }[]
    }
    expect(body.replayed).toEqual([])
    expect(body.irreversible).toEqual([])
    expect(body.failed).toEqual([
      { event_id: "evt-write-1", reason: "缺少操作目标信息（文件路径），无法撤销 write_file" },
    ])
  })

  test("POST returns irreversible for send_email (no undo attempted)", async () => {
    const now = new Date()
    const events: readonly AuditEventRecord[] = [
      {
        auditId: "evt-send-1",
        runId: null,
        conversationId: null,
        // D72 T1: see write_file fixture above.
        actor: "owner",
        action: "fatigue.decision",
        subject: "send_email",
        detail: {},
        createdAt: now,
        correlationId: null,
      },
    ]
    const wiring = makeWiring(makeMockRuntimeStore(events))
    const app = makeHonoWithAuditFatigue(wiring)
    const res = await app.request("/v1/owner/audit/fatigue/replay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sequence_event_ids: ["evt-send-1"] }),
    })
    expect(res.status).toBe(200)
    const body = (await res.json()) as {
      replayed: string[]
      irreversible: string[]
      failed: { event_id: string; reason: string }[]
    }
    expect(body.replayed).toEqual([])
    expect(body.irreversible).toEqual(["evt-send-1"])
    expect(body.failed).toEqual([])
  })

  test("POST emits owner.replay audit_event after replay (D69 T5 SO-16 mirror)", async () => {
    const appendAuditEvent = vi.fn(async () => undefined)
    const wiring = makeWiring({
      listRecentAuditEvents: vi.fn(async () => []),
      appendAuditEvent,
    } as unknown as RuntimeStore)
    const app = makeHonoWithAuditFatigue(wiring)
    await app.request("/v1/owner/audit/fatigue/replay", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sequence_event_ids: ["evt-missing"] }),
    })
    expect(appendAuditEvent).toHaveBeenCalledTimes(1)
    const call = appendAuditEvent.mock.calls[0]?.[0] as {
      action: string
      subject: string
      detail: { sequence_event_ids: string[]; replayed: number; irreversible: number; failed: number }
    }
    expect(call.action).toBe("owner.replay")
    expect(call.subject).toBe("owner")
    expect(call.detail.sequence_event_ids).toEqual(["evt-missing"])
  })
})
