/**
 * WebSocket push routes — R8.x.8.
 *
 * Maintains a registry of `conversationId → Set<ws>` so that when a
 * subagent reply (or any other event_store write for a conversation)
 * hits the parent stream, we can push it in real-time to every
 * connected client subscribed to that conversation.
 *
 * Architecture:
 *   - The WS server is a standalone `ws.Server` listening on its
 *     own port (default 3001, configurable via `WS_PORT`). The Hono
 *     HTTP API stays on its own port (3000) — the two share the
 *     same process but never share a socket. This keeps the wiring
 *     simple: the CLI doesn't need to know about WS, and the v5
 *     route handler stays HTTP-only.
 *   - Clients open `ws://host:port/?conversationId=<id>` and receive
 *     a `connected` frame on open, then `event` frames for every
 *     push. `ping`/`pong` keepalives are supported.
 *   - `pushEventToSubscribers` is the shared push API. The subagent
 *     worker calls it after writing an `AssistantMessageProduced`
 *     to the parent stream — see `subagent-worker.ts`. The WS
 *     server keeps the same registry so test code can call the
 *     push function directly (no real network round-trip needed).
 *
 * Constraints honored:
 *   - No `throw` anywhere (errors are caught + logged).
 *   - No `// ts-prune-ignore-next` annotations.
 *   - All new code lives in `apps/api/src/`.
 */
import { createServer, type Server as HttpServer } from "node:http"
import { WebSocketServer, type WebSocket as WsWebSocket } from "ws"
import { lookupSubscribeToken } from "./ws-subscribe.js"

const DEFAULT_WS_PORT = 3001
const WS_PATH_PREFIX = "/v1/ws"

/**
 * Subscriber registry keyed by `conversationId`. Each value is the
 * set of currently-connected WS clients subscribed to that
 * conversation. Empty sets are removed so `size` checks stay cheap.
 *
 * Exported as a Map so test code can introspect it (e.g. to assert
 * the registry shrinks after a client disconnects).
 */
export const subscribers: Map<string, Set<WsWebSocket>> = new Map()

/**
 * Frame envelope shape for every message the server sends.
 * `kind: "connected"` is a one-shot on-open greeting; `kind: "event"`
 * wraps a push; `kind: "pong"` answers a client ping.
 */
export type WsOutboundFrame =
  | { readonly kind: "connected"; readonly conversationId: string }
  | { readonly kind: "event"; readonly conversationId: string; readonly event: unknown }
  | { readonly kind: "pong" }
  | { readonly kind: "error"; readonly reason: string }

/**
 * Minimal console logger used by the WS server. Keeps the module
 * dependency-free (the real v5 process can wire its own logger via
 * `Wiring` if it wants to later).
 */
const wsLogger = {
  info: (msg: string, extra?: unknown) => {
    // eslint-disable-next-line no-console -- intentional stderr log
    console.warn(msg, extra ?? "")
  },
  error: (msg: string, extra?: unknown) => {
    // eslint-disable-next-line no-console -- intentional stderr log
    console.error(msg, extra ?? "")
  },
}

/**
 * Push an event to every subscriber of `conversationId`. Safe to
 * call when no subscribers are registered (no-op). Errors while
 * serializing or sending to an individual socket are swallowed so
 * one stuck client can't break the others.
 *
 * Returns the number of clients the event was actually delivered
 * to (handy for logs + assertions in tests).
 */
export function pushEventToSubscribers(conversationId: string, event: unknown): number {
  const set = subscribers.get(conversationId)
  if (!set || set.size === 0) return 0
  const frame: WsOutboundFrame = { kind: "event", conversationId, event }
  let payload: string
  try {
    payload = JSON.stringify(frame)
  } catch (err) {
    wsLogger.error(`[ws-routes] failed to serialize event for ${conversationId}:`, err)
    return 0
  }
  let delivered = 0
  for (const ws of set) {
    // WsWebSocket.OPEN === 1
    if (ws.readyState === 1) {
      try {
        ws.send(payload)
        delivered += 1
      } catch (err) {
        wsLogger.error(`[ws-routes] send failed for subscriber of ${conversationId}:`, err)
      }
    }
  }
  return delivered
}

/**
 * Register a single subscriber in the registry. Returns a teardown
 * function the caller must invoke when the WS closes (idempotent —
 * safe to call more than once).
 */
function registerSubscriber(conversationId: string, ws: WsWebSocket): () => void {
  let set = subscribers.get(conversationId)
  if (!set) {
    set = new Set()
    subscribers.set(conversationId, set)
  }
  set.add(ws)
  let torn = false
  return () => {
    if (torn) return
    torn = true
    const current = subscribers.get(conversationId)
    if (!current) return
    current.delete(ws)
    if (current.size === 0) {
      subscribers.delete(conversationId)
    }
  }
}

export function extractQueryParam(url: string, name: string): string {
  const qIndex = url.indexOf("?")
  if (qIndex < 0) return ""
  const query = url.slice(qIndex + 1)
  for (const part of query.split("&")) {
    const eq = part.indexOf("=")
    if (eq < 0) continue
    const k = part.slice(0, eq)
    if (k !== name) continue
    const raw = part.slice(eq + 1)
    try {
      return decodeURIComponent(raw)
    } catch {
      return raw
    }
  }
  return ""
}

/**
 * Parse `conversationId` from a URL query string. Returns "" when
 * missing or when the query string is malformed (the caller then
 * closes the socket with a 1008 — policy violation).
 */
export function extractConversationId(url: string): string {
  return extractQueryParam(url, "conversationId")
}

export type WsIdentity =
  | { readonly ok: true; readonly conversationId: string }
  | { readonly ok: false; readonly reason: string }

export function resolveWsIdentity(url: string): WsIdentity {
  const token = extractQueryParam(url, "token")
  const conversationId = extractConversationId(url)
  if (token) {
    const rec = lookupSubscribeToken(token)
    if (!rec) {
      return { ok: false, reason: "invalid or expired token" }
    }
    if (conversationId && conversationId !== rec.conversationId) {
      return { ok: false, reason: "token conversationId mismatch" }
    }
    return { ok: true, conversationId: rec.conversationId }
  }
  if (!conversationId) {
    return { ok: false, reason: "missing conversationId" }
  }
  return { ok: true, conversationId }
}

export interface WsServerHandle {
  readonly port: number
  readonly url: string
  readonly close: () => Promise<void>
}

/**
 * Build a `ws.WebSocketServer` in `noServer` mode and wire it to
 * `server`'s `upgrade` event for `WS_PATH_PREFIX`. Returns the
 * resulting `WsServerHandle`.
 *
 * This is the public seam tests use to spin up a WS server bound
 * to a deterministic port without touching the v5 entry point.
 */
export async function startWsServer(
  opts: { readonly port?: number; readonly host?: string } = {},
): Promise<WsServerHandle> {
  const port = opts.port ?? DEFAULT_WS_PORT
  const host = opts.host ?? "127.0.0.1"
  const wss = new WebSocketServer({ noServer: true })
  wss.on("connection", (ws, req) => {
    const identity = resolveWsIdentity(req.url ?? "")
    if (!identity.ok) {
      ws.close(1008, identity.reason)
      return
    }
    const conversationId = identity.conversationId
    const teardown = registerSubscriber(conversationId, ws)
    try {
      const greeting: WsOutboundFrame = { kind: "connected", conversationId }
      ws.send(JSON.stringify(greeting))
    } catch (err) {
      wsLogger.error(`[ws-routes] failed to send greeting for ${conversationId}:`, err)
    }
    ws.on("message", (raw) => {
      // Heartbeat / client messages. `ws` delivers as Buffer by
      // default — decode to string first so the JSON parser sees
      // the same shape the test client sends.
      let text: string
      if (typeof raw === "string") {
        text = raw
      } else if (Buffer.isBuffer(raw)) {
        text = raw.toString("utf8")
      } else {
        return
      }
      try {
        const parsed = JSON.parse(text) as { kind?: unknown }
        if (parsed.kind === "ping") {
          const pong: WsOutboundFrame = { kind: "pong" }
          ws.send(JSON.stringify(pong))
        }
      } catch {
        // ignore malformed frames
      }
    })
    ws.on("close", () => {
      teardown()
    })
    ws.on("error", (err) => {
      wsLogger.error(`[ws-routes] socket error for ${conversationId}:`, err)
      teardown()
    })
  })

  const server: HttpServer = createServer((req, res) => {
    // Non-upgrade requests get a 404 (the WS path is the only thing
    // this server speaks).
    if (req.url && req.url.startsWith(WS_PATH_PREFIX)) {
      res.statusCode = 426
      res.setHeader("Upgrade", "websocket")
      res.end("upgrade required")
      return
    }
    res.statusCode = 404
    res.end("not found")
  })
  server.on("upgrade", (req, socket, head) => {
    if (!req.url || !req.url.startsWith(WS_PATH_PREFIX)) {
      socket.destroy()
      return
    }
    // With `noServer: true`, the ws library does NOT auto-emit
    // the `connection` event — we have to wire it up explicitly.
    // The callback receives the constructed WebSocket instance
    // after the handshake completes; we re-emit so the standard
    // `wss.on('connection', ...)` handler runs.
    wss.handleUpgrade(req, socket, head, (ws) => {
      wss.emit("connection", ws, req)
    })
  })

  return new Promise<WsServerHandle>((resolve) => {
    server.once("error", (err) => {
      wsLogger.error(`[ws-routes] listen failed on ${host}:${port}:`, err)
    })
    server.listen(port, host, () => {
      // Resolve the actual bound port — `port: 0` requests an
      // ephemeral port and `server.address()` reports it.
      const addr = server.address()
      const boundPort = addr && typeof addr === "object" && "port" in addr ? addr.port : port
      const boundHost = host
      wsLogger.info(`[ws-routes] listening on ws://${boundHost}:${boundPort}${WS_PATH_PREFIX}`)
      resolve({
        port: boundPort,
        url: `ws://${boundHost}:${boundPort}${WS_PATH_PREFIX}`,
        close: () =>
          new Promise<void>((done) => {
            wss.close(() => {
              server.close(() => {
                done()
              })
            })
          }),
      })
    })
  })
}

/**
 * Clear all subscribers (used by tests in `beforeEach` so a stale
 * registration from a previous suite doesn't leak across cases).
 */
export function clearAllSubscribers(): void {
  subscribers.clear()
}
