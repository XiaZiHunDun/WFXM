import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

import { default as app, __wiring__ } from "@butler/api"

// @hono/node-server resolution anchored at cli/package.json (workspace-internal)
const cliRequire = createRequire(fileURLToPath(new URL("../../cli/package.json", import.meta.url)))

interface AddressInfoLike {
  readonly port: number
}
interface NodeServer {
  close(cb?: (err?: Error) => void): unknown
}
interface ServeOptions {
  fetch: (request: Request, env?: unknown) => Response | Promise<Response>
  port?: number
}
type ServeFn = (
  options: ServeOptions,
  listeningListener?: (info: AddressInfoLike) => void,
) => NodeServer

const { serve } = cliRequire("@hono/node-server") as { serve: ServeFn }

let server: NodeServer | undefined
let baseUrl = ""

beforeAll(async () => {
  await new Promise<void>((resolve) => {
    server = serve({ fetch: app.fetch, port: 0 }, (info) => {
      baseUrl = `http://127.0.0.1:${info.port}`
      resolve()
    })
  })
})

afterAll(async () => {
  if (!server) return
  await new Promise<void>((resolve) => {
    server.close(() => resolve())
  })
})

describe("R8 real-path persistence", () => {
  it("POST /v1/conversations persists exactly one event with full envelope projection", async () => {
    const res = await fetch(`${baseUrl}/v1/conversations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        projectId: "p-r8-persist",
        content: "real-path write",
      }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as { conversationId?: string }
    const streamId = body.conversationId as string

    const events = await __wiring__.eventBridge.loadStream(streamId)
    expect(events).toHaveLength(1)
    const event = events[0]
    expect(event).toBeDefined()
    expect(event?.streamId).toBe(streamId)
    expect(event?.streamVersion).toBe(1)
    expect(event?.eventType).toBe("ConversationStarted")
    expect(event?.actorKind).toBe("system")
    expect(event?.actorId).toBe("wiring")
    expect(event?.correlationId).toMatch(/^corr-/)
  })

  it("two POST /v1/conversations get distinct stream_ids, each at version 1", async () => {
    const projectId = "p-r8-versioning"
    const postOnce = async (content: string) => {
      const r = await fetch(`${baseUrl}/v1/conversations`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ apiVersion: "v1", projectId, content }),
      })
      expect(r.status).toBe(201)
      return (await r.json()) as { conversationId?: string }
    }

    const first = await postOnce("first turn")
    const firstEvents = await __wiring__.eventBridge.loadStream(first.conversationId as string)
    expect(firstEvents[0]?.streamVersion).toBe(1)

    // routes.ts generates a fresh conversationId per request via Date.now(),
    // so two POSTs against the same project produce two distinct streams,
    // each containing exactly one event at version 1 (per-stream monotonic,
    // cross-stream isolated).
    const second = await postOnce("second turn")
    const secondEvents = await __wiring__.eventBridge.loadStream(second.conversationId as string)
    expect(secondEvents[0]?.streamVersion).toBe(1)
    expect(secondEvents[0]?.streamId).not.toBe(firstEvents[0]?.streamId)
  })

  it("appendConversationEventWithOutbox writes event + outbox row that runWorker can claim and deliver", async () => {
    // D7-arch-align §20 #8: outbox is only written via the tx-composing
    // EventBridge.appendConversationEventWithOutbox. Direct enqueue is no
    // longer exposed on EventBridge (it would create orphan outbox rows
    // outside the state-change transaction).
    const streamId = "outbox-r8-test"
    const messageId = await __wiring__.eventBridge.appendConversationEventWithOutbox({
      streamId,
      event: { _tag: "TestEvent", at: new Date().toISOString() },
      eventId: crypto.randomUUID(),
      eventType: "TestEvent",
      correlationId: "corr-r8",
      actor: { kind: "system", id: "e2e" },
      outbox: {
        aggregateType: "test-aggregate",
        payload: { kind: "r8-real-persistence", at: new Date().toISOString() },
      },
    })
    expect(typeof messageId).toBe("string")

    // runWorker wraps runWorkerOnce: it claims pending outbox rows, runs
    // the handler for each, and marks them delivered. If the outbox row
    // wasn't written, claim returns 0 and the handler never runs.
    let claimed = 0
    const delivered = await __wiring__.eventBridge.runWorker(async () => {
      claimed += 1
    })
    expect(claimed).toBeGreaterThanOrEqual(1)
    expect(delivered).toBeGreaterThanOrEqual(1)
  })
})
