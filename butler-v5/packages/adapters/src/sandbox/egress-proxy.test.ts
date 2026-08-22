import { createServer } from "node:http"
import { connect as netConnect } from "node:net"
import { request as httpRequest } from "node:http"
import { describe, expect, it, afterEach } from "vitest"
import { startEgressAllowlistProxy } from "./egress-proxy.js"

describe("egress allowlist proxy", () => {
  let proxy: Awaited<ReturnType<typeof startEgressAllowlistProxy>> | undefined
  let echoServer: ReturnType<typeof createServer> | undefined
  let echoPort = 0

  afterEach(async () => {
    await proxy?.close()
    proxy = undefined
    await new Promise<void>((resolve) => {
      if (echoServer) echoServer.close(() => resolve())
      else resolve()
    })
    echoServer = undefined
  })

  async function startEchoServer(): Promise<number> {
    echoServer = createServer((_req, res) => {
      res.writeHead(200)
      res.end("echo-ok")
    })
    await new Promise<void>((resolve) => {
      if (!echoServer) {
        resolve()
        return
      }
      echoServer.listen(0, "127.0.0.1", () => resolve())
    })
    const addr = echoServer?.address()
    echoPort = typeof addr === "object" && addr ? addr.port : 0
    return echoPort
  }

  function proxyPort(): number {
    if (!proxy) return 0
    return Number(proxy.proxyUrl.split(":").at(-1))
  }

  it("allows HTTP GET via proxy to allowlisted host:port", async () => {
    const port = await startEchoServer()
    proxy = await startEgressAllowlistProxy([`127.0.0.1:${port}`])
    const body = await new Promise<string>((resolve, reject) => {
      const req = httpRequest(
        {
          host: "127.0.0.1",
          port: proxyPort(),
          method: "GET",
          path: `http://127.0.0.1:${port}/`,
          headers: { Host: `127.0.0.1:${port}` },
        },
        (res) => {
          const chunks: Buffer[] = []
          res.on("data", (c) => chunks.push(c as Buffer))
          res.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")))
        },
      )
      req.on("error", reject)
      req.end()
    })
    expect(body).toContain("echo-ok")
  })

  it("denies CONNECT to non-allowlisted destination", async () => {
    const port = await startEchoServer()
    proxy = await startEgressAllowlistProxy(["example.com:443"])
    const denied = await new Promise<string>((resolve) => {
      const socket = netConnect(proxyPort(), "127.0.0.1")
      socket.write(`CONNECT 127.0.0.1:${port} HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\n\r\n`)
      socket.on("data", (buf) => {
        resolve(buf.toString("utf8"))
        socket.destroy()
      })
      socket.on("error", () => resolve("error"))
    })
    expect(denied).toContain("403")
  })
})
