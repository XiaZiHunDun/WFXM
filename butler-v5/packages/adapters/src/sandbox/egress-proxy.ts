import { createServer, type IncomingMessage, type ServerResponse } from "node:http"
import { connect as netConnect, type Socket } from "node:net"
import { isDestinationAllowedInNetworkAllowlist } from "@butler/domain/governance/network-allowlist.js"

export interface EgressProxyHandle {
  readonly proxyUrl: string
  readonly close: () => Promise<void>
}

export function resolveEgressUpstreamProxy(
  env: Readonly<Record<string, string | undefined>> = process.env,
): string | undefined {
  const explicit = (env["BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY"] ?? "").trim()
  if (explicit) return explicit
  const raw = env["HTTPS_PROXY"] ?? env["https_proxy"] ?? env["HTTP_PROXY"] ?? env["http_proxy"]
  const trimmed = (raw ?? "").trim()
  return trimmed || undefined
}

function writeConnectDenied(socket: Socket): void {
  socket.write("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
  socket.destroy()
}

function pipeSockets(a: Socket, b: Socket): void {
  a.pipe(b)
  b.pipe(a)
  a.on("error", () => {
    a.destroy()
    b.destroy()
  })
  b.on("error", () => {
    a.destroy()
    b.destroy()
  })
}

function parseHostPortFromConnectTarget(target: string): { host: string; port: number } | null {
  const trimmed = target.trim()
  if (!trimmed) return null
  const lastColon = trimmed.lastIndexOf(":")
  if (lastColon <= 0) {
    return { host: trimmed, port: 443 }
  }
  const host = trimmed.slice(0, lastColon)
  const portPart = trimmed.slice(lastColon + 1)
  if (!/^\d+$/.test(portPart)) return null
  const port = Number(portPart)
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null
  return { host, port }
}

function dialThroughUpstreamConnect(
  host: string,
  port: number,
  upstreamProxyUrl: string,
  onReady: (socket: Socket, pending: Buffer) => void,
  onError: () => void,
): void {
  let parsed: URL
  try {
    parsed = new URL(upstreamProxyUrl)
  } catch {
    onError()
    return
  }
  const proxyPort = parsed.port ? Number(parsed.port) : parsed.protocol === "https:" ? 443 : 80
  const proxy = netConnect(proxyPort, parsed.hostname)
  proxy.once("error", onError)
  proxy.once("connect", () => {
    proxy.write(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`)
    let buffer = Buffer.alloc(0)
    const onData = (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk])
      const marker = buffer.indexOf("\r\n\r\n")
      if (marker < 0) return
      proxy.off("data", onData)
      const headerText = buffer.subarray(0, marker).toString("utf8")
      if (!headerText.includes("200")) {
        onError()
        proxy.destroy()
        return
      }
      onReady(proxy, buffer.subarray(marker + 4))
    }
    proxy.on("data", onData)
  })
}

function dialAllowlistedTarget(
  host: string,
  port: number,
  upstreamProxyUrl: string | undefined,
  onReady: (socket: Socket, pending: Buffer) => void,
  onError: () => void,
): void {
  if (upstreamProxyUrl) {
    dialThroughUpstreamConnect(host, port, upstreamProxyUrl, onReady, onError)
    return
  }
  const upstream = netConnect(port, host)
  upstream.once("error", onError)
  upstream.once("connect", () => onReady(upstream, Buffer.alloc(0)))
}

function handleHttpForward(
  req: IncomingMessage,
  res: ServerResponse,
  allowlist: readonly string[],
  upstreamProxyUrl?: string,
): void {
  const rawUrl = req.url ?? ""
  if (!rawUrl.startsWith("http://")) {
    res.writeHead(400)
    res.end("bad request")
    return
  }
  let parsed: URL
  try {
    parsed = new URL(rawUrl)
  } catch {
    res.writeHead(400)
    res.end("bad url")
    return
  }
  const port = parsed.port ? Number(parsed.port) : 80
  if (!isDestinationAllowedInNetworkAllowlist(parsed.hostname, port, allowlist)) {
    res.writeHead(403)
    res.end("forbidden")
    return
  }
  dialAllowlistedTarget(
    parsed.hostname,
    port,
    upstreamProxyUrl,
    (upstream, pending) => {
      const path = `${parsed.pathname}${parsed.search}`
      const headers = { ...req.headers, host: parsed.host }
      delete headers["proxy-connection"]
      upstream.write(`${req.method ?? "GET"} ${path} HTTP/1.1\r\n`)
      for (const [key, value] of Object.entries(headers)) {
        if (value === undefined) continue
        if (Array.isArray(value)) {
          for (const v of value) upstream.write(`${key}: ${v}\r\n`)
        } else {
          upstream.write(`${key}: ${value}\r\n`)
        }
      }
      upstream.write("\r\n")
      if (pending.length > 0) upstream.write(pending)
      req.pipe(upstream)
      upstream.on("data", (chunk) => res.write(chunk))
      upstream.on("end", () => res.end())
      upstream.on("error", () => {
        if (!res.headersSent) res.writeHead(502)
        res.end("bad gateway")
      })
    },
    () => {
      if (!res.headersSent) res.writeHead(502)
      res.end("bad gateway")
    },
  )
}

/**
 * Minimal HTTP CONNECT proxy enforcing Grant host:port allowlist (P2c MVP).
 * HTTPS clients that honor HTTPS_PROXY are filtered; raw TCP bypass is P2d scope.
 */
export async function startEgressAllowlistProxy(
  allowlist: readonly string[],
  options: {
    readonly listenHost?: string
    readonly env?: Readonly<Record<string, string | undefined>>
  } = {},
): Promise<EgressProxyHandle> {
  if (allowlist.length === 0) {
    throw new Error("egress proxy requires non-empty allowlist")
  }
  const listenHost = options.listenHost ?? "127.0.0.1"
  const upstreamProxyUrl = resolveEgressUpstreamProxy(options.env)
  const server = createServer((req, res) =>
    handleHttpForward(req, res, allowlist, upstreamProxyUrl),
  )

  server.on("connect", (req, clientSocket, head) => {
    const socket = clientSocket as Socket
    const target = parseHostPortFromConnectTarget(req.url ?? "")
    if (!target) {
      writeConnectDenied(socket)
      return
    }
    if (!isDestinationAllowedInNetworkAllowlist(target.host, target.port, allowlist)) {
      writeConnectDenied(socket)
      return
    }
    dialAllowlistedTarget(
      target.host,
      target.port,
      upstreamProxyUrl,
      (upstream, pending) => {
        socket.write("HTTP/1.1 200 Connection Established\r\n\r\n")
        const initial = Buffer.concat([pending, head])
        if (initial.length > 0) upstream.write(initial)
        pipeSockets(socket, upstream)
      },
      () => writeConnectDenied(socket),
    )
  })

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    server.listen(0, listenHost, () => resolve())
  })

  const address = server.address()
  const port = typeof address === "object" && address ? address.port : 0
  if (!port) {
    server.close()
    throw new Error("egress proxy failed to bind")
  }

  return {
    proxyUrl: `http://${listenHost}:${port}`,
    close: () =>
      new Promise((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()))
      }),
  }
}

export function buildSandboxProxyEnv(proxyUrl: string): Record<string, string> {
  return {
    HTTP_PROXY: proxyUrl,
    HTTPS_PROXY: proxyUrl,
    http_proxy: proxyUrl,
    https_proxy: proxyUrl,
    NO_PROXY: "",
    no_proxy: "",
  }
}
