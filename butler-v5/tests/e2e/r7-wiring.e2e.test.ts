import { describe, expect, it, vi, afterAll, beforeAll } from "vitest"
import { createRequire } from "node:module"
import { fileURLToPath } from "node:url"

// The apps/api Hono app instantiates an in-process pglite via
// `new PGlite()` at module top level without running the schema migration,
// so its event_store / outbox relations do not exist. A live
// appendConversationEvent therefore throws on the first write and the
// POST handler surfaces as 500. Stubbing the bridge here lets the e2e
// test exercise the Hono + @hono/node-server wiring through a real socket
// while keeping the persistence layer out of scope for this gate.
// vi.mock is hoisted above the imports, so the path must be a literal.
vi.mock("../../packages/runtime/src/bridge.ts", () => ({
  EventBridge: class {
    async appendConversationEvent(): Promise<void> {
      // no-op stub: contract satisfied, persistence intentionally not exercised
    }
  },
}))

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
  const { default: app } = await import("@butler/api")
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

  it("POST /v1/conversations with valid body returns 201", async () => {
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
