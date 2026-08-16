/**
 * WebSocket routes tests — R8.x.8.
 *
 * Exercises:
 *   - Client upgrade handshake + `connected` greeting
 *   - `ping`/`pong` keepalive
 *   - `pushEventToSubscribers` fan-out to subscribers of matching
 *     conversationId
 *   - No delivery for non-matching conversationId
 *   - Subscriber registry shrinks on close
 *   - Server close() shuts down cleanly
 *
 * Uses a real `ws` client against the in-process server so we
 * exercise the upgrade path end-to-end (no in-process mocks for
 * the transport layer).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import WebSocket from "ws"
import {
  clearAllSubscribers,
  extractConversationId,
  pushEventToSubscribers,
  startWsServer,
  subscribers,
  type WsServerHandle,
} from "./ws-routes.js"

async function waitForOpen(ws: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    ws.once("open", () => resolve())
    ws.once("error", (err) => reject(err))
  })
}

interface TestClient {
  readonly ws: WebSocket
  readonly nextFrame: () => Promise<unknown>
  readonly close: () => void
}

function openClient(url: string): TestClient {
  const ws = new WebSocket(url)
  // Buffer frames so a message that arrives before `nextFrame()` is
  // called doesn't get dropped (the server sends the greeting
  // inside the `connection` handler, often before the client
  // calls into `nextFrame()`).
  const buffer: unknown[] = []
  const waiters: ((v: unknown) => void)[] = []
  ws.on("message", (data) => {
    const raw = data.toString()
    let parsed: unknown = raw
    try {
      parsed = JSON.parse(raw)
    } catch {
      // keep raw
    }
    const waiter = waiters.shift()
    if (waiter) {
      waiter(parsed)
    } else {
      buffer.push(parsed)
    }
  })
  return {
    ws,
    nextFrame: () =>
      new Promise<unknown>((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new Error("timeout: no frame received"))
        }, 3_000)
        const deliver = (v: unknown): void => {
          clearTimeout(timer)
          resolve(v)
        }
        const buffered = buffer.shift()
        if (buffered !== undefined) {
          deliver(buffered)
          return
        }
        waiters.push(deliver)
      }),
    close: () => {
      ws.close()
    },
  }
}

describe("ws-routes — extractConversationId", () => {
  it("parses conversationId from a single-param query string", () => {
    expect(extractConversationId("/v1/ws?conversationId=abc-123")).toBe("abc-123")
  })

  it("decodes URL-encoded values", () => {
    expect(extractConversationId("/v1/ws?conversationId=a%20b")).toBe("a b")
  })

  it("returns empty when the query string is missing", () => {
    expect(extractConversationId("/v1/ws")).toBe("")
  })

  it("returns empty when conversationId is absent but other params present", () => {
    expect(extractConversationId("/v1/ws?foo=bar")).toBe("")
  })
})

describe("ws-routes — pushEventToSubscribers", () => {
  beforeEach(() => {
    clearAllSubscribers()
  })

  it("returns 0 when no subscribers are registered", () => {
    const delivered = pushEventToSubscribers("never-subscribed", { hello: "world" })
    expect(delivered).toBe(0)
  })

  it("swallows circular reference serialization errors without crashing", () => {
    // No subscribers — should still return 0 without throwing.
    const obj: Record<string, unknown> = {}
    obj["self"] = obj
    const delivered = pushEventToSubscribers("none", obj)
    expect(delivered).toBe(0)
  })
})

describe("ws-routes — WebSocket server", () => {
  let handle: WsServerHandle | undefined

  beforeEach(async () => {
    clearAllSubscribers()
    handle = await startWsServer({ port: 0, host: "127.0.0.1" })
  })

  afterEach(async () => {
    if (handle) {
      await handle.close()
      handle = undefined
    }
    clearAllSubscribers()
  })

  function url(): string {
    // Resolve the URL at call time so the lint rule banning
    // non-null assertions is satisfied without losing the
    // beforeEach assignment.
    return handle ? handle.url : ""
  }

  it("sends a `connected` greeting on upgrade with a valid conversationId", async () => {
    const baseUrl = await url()
    const client = openClient(`${baseUrl}?conversationId=c-greet`)
    await waitForOpen(client.ws)
    const greeting = (await client.nextFrame()) as { kind: string; conversationId: string }
    expect(greeting.kind).toBe("connected")
    expect(greeting.conversationId).toBe("c-greet")
    client.close()
  })

  it("answers `ping` with `pong`", async () => {
    const baseUrl = await url()
    const client = openClient(`${baseUrl}?conversationId=c-ping`)
    await waitForOpen(client.ws)
    // First frame is the greeting; drain it.
    await client.nextFrame()
    client.ws.send(JSON.stringify({ kind: "ping" }))
    const pong = (await client.nextFrame()) as { kind: string }
    expect(pong.kind).toBe("pong")
    client.close()
  })

  it("delivers an event to all subscribers of the matching conversationId", async () => {
    const baseUrl = await url()
    const a = openClient(`${baseUrl}?conversationId=c-fanout`)
    const b = openClient(`${baseUrl}?conversationId=c-fanout`)
    await Promise.all([waitForOpen(a.ws), waitForOpen(b.ws)])
    // Drain the two greetings.
    await Promise.all([a.nextFrame(), b.nextFrame()])
    expect(subscribers.get("c-fanout")?.size).toBe(2)

    const delivered = pushEventToSubscribers("c-fanout", { text: "hello" })
    expect(delivered).toBe(2)

    const [aFrame, bFrame] = await Promise.all([a.nextFrame(), b.nextFrame()])
    expect((aFrame as { kind: string }).kind).toBe("event")
    expect((bFrame as { kind: string }).kind).toBe("event")
    a.close()
    b.close()
  })

  it("does not deliver events to subscribers of a different conversationId", async () => {
    const baseUrl = await url()
    const client = openClient(`${baseUrl}?conversationId=c-other`)
    await waitForOpen(client.ws)
    await client.nextFrame() // drain greeting

    const delivered = pushEventToSubscribers("c-mismatch", { text: "ignored" })
    expect(delivered).toBe(0)

    // Wait briefly and confirm no extra frame arrived.
    const race = await Promise.race([
      client.nextFrame().then(() => "arrived"),
      new Promise((r) => setTimeout(() => r("timeout"), 200)),
    ])
    expect(race).toBe("timeout")
    client.close()
  })

  it("removes the subscriber from the registry when the socket closes", async () => {
    const baseUrl = await url()
    const client = openClient(`${baseUrl}?conversationId=c-cleanup`)
    await waitForOpen(client.ws)
    await client.nextFrame() // drain greeting
    expect(subscribers.get("c-cleanup")?.size).toBe(1)

    const closed = new Promise<void>((resolve) => {
      client.ws.once("close", () => resolve())
    })
    client.close()
    await closed
    // Give the server a tick to run the close handler.
    await new Promise((r) => setTimeout(r, 20))
    expect(subscribers.has("c-cleanup")).toBe(false)
  })

  it("closes with 1008 when the client omits conversationId", async () => {
    const baseUrl = await url()
    const client = openClient(`${baseUrl}`)
    await waitForOpen(client.ws)
    const closeInfo = await new Promise<{ code: number }>((resolve) => {
      client.ws.once("close", (code) => resolve({ code }))
    })
    expect(closeInfo.code).toBe(1008)
  })

  it("close() is idempotent", async () => {
    if (!handle) {
      // Use a rejected promise instead of `throw` per the "no
      // throw in new code" rule.
      await Promise.reject(new Error("handle missing"))
      return
    }
    await handle.close()
    // Second close should resolve without throwing.
    await handle.close()
  })
})
