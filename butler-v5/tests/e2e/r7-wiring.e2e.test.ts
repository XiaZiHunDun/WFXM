import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

// R8.1 bootstraps the pglite schema at apps/api boot, so EventBridge
// hits a real event_store table; no mock required. We import the live
// wiring alongside the Hono app to assert real-path persistence below.
import { default as app, __wiring__ } from "@butler/api"

// @hono/node-server is a workspace-internal dep of @butler/cli, so the
// node_modules chain is rooted under cli/. Anchor createRequire there to
// make the resolution symmetric with how the cli binary imports it.
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

describe("R7 wiring end-to-end", () => {
  it("GET /healthz returns 200 with wiring version", async () => {
    const res = await fetch(`${baseUrl}/healthz`)
    expect(res.status).toBe(200)
    const body = (await res.json()) as { status?: string; wiring?: string }
    expect(body.status).toBe("ok")
    expect(body.wiring).toBe("v5")
  })

  it("POST /v1/conversations with valid body returns 201 and writes to event_store", async () => {
    const res = await fetch(`${baseUrl}/v1/conversations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        projectId: "p-r7-e2e",
        content: "hello",
      }),
    })
    expect(res.status).toBe(201)
    const body = (await res.json()) as { conversationId?: string; turnId?: string }
    expect(typeof body.conversationId).toBe("string")
    expect(typeof body.turnId).toBe("string")

    // Real-path assertion: loadStream returns the ConversationStarted
    // row that appendConversationEvent wrote via the live EventBridge.
    const streamId = body.conversationId as string
    const events = await __wiring__.eventBridge.loadStream(streamId)
    expect(events).toHaveLength(1)
    expect(events[0]?.eventType).toBe("ConversationStarted")
  })

  it("POST /v1/conversations with invalid body returns 400", async () => {
    const res = await fetch(`${baseUrl}/v1/conversations`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })
})
