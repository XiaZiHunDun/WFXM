import { describe, expect, it } from "vitest"
import {
  findMcpServer,
  mcpServerIds,
  parseMcpManifest,
  preScanMcpManifest,
  preScanMcpServer,
  resolveManifestStdioArgs,
} from "./manifest.js"

describe("MCP manifest", () => {
  it("parses server provider metadata skeleton", () => {
    const parsed = parseMcpManifest({
      version: 1,
      servers: [
        {
          id: "github",
          transport: "stdio",
          command: "node",
          defaultRisk: "low",
          auditPolicy: "full",
          defaultSandboxProfile: "workspace-write-network-deny",
          tools: [{ name: "search_repositories", risk: "low" }],
        },
      ],
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    const server = findMcpServer(parsed.value, "github")
    expect(server?.defaultRisk).toBe("low")
    expect(server?.auditPolicy).toBe("full")
    expect(server?.defaultSandboxProfile).toBe("workspace-write-network-deny")
  })

  it("parses server entries", () => {
    const parsed = parseMcpManifest({
      version: 1,
      servers: [
        {
          id: "local",
          transport: "stdio",
          command: "node",
          tools: [{ name: "search", risk: "high" }],
        },
      ],
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(mcpServerIds(parsed.value)).toEqual(["local"])
    expect(findMcpServer(parsed.value, "local")?.command).toBe("node")
    expect(parsed.value.servers[0]?.tools?.[0]?.name).toBe("search")
  })

  it("rejects invalid transport", () => {
    expect(
      parseMcpManifest({ version: 1, servers: [{ id: "x", transport: "ws" }] }).ok,
    ).toBe(false)
  })

  it("resolves --openapi-spec paths relative to manifest directory", () => {
    const resolved = resolveManifestStdioArgs("/repo/butler-v5/config/mcp-manifest.json", [
      "--api-base-url",
      "https://api.todoist.com",
      "--openapi-spec",
      "openapi/todoist-v1-readonly.yml",
    ])
    expect(resolved).toEqual([
      "--api-base-url",
      "https://api.todoist.com",
      "--openapi-spec",
      "/repo/butler-v5/config/openapi/todoist-v1-readonly.yml",
    ])
  })

  it("leaves absolute --openapi-spec paths unchanged", () => {
    const abs = "/abs/todoist.yml"
    const resolved = resolveManifestStdioArgs("/repo/config/mcp.json", ["--openapi-spec", abs])
    expect(resolved).toEqual(["--openapi-spec", abs])
  })
})

describe("P3-3 pre-install scan", () => {
  it("accepts a clean stdio server", () => {
    expect(
      preScanMcpServer({ id: "node", transport: "stdio", command: "node ./server.mjs", tools: [] }),
    ).toEqual({ ok: true })
  })

  it("refuses a stdio server that would launch a shell", () => {
    expect(preScanMcpServer({ id: "s", transport: "stdio", command: "bash", tools: [] })).toMatchObject({
      ok: false,
    })
    expect(preScanMcpServer({ id: "s", transport: "stdio", command: "node -e x && curl", tools: [] })).toMatchObject({
      ok: false,
    })
  })

  it("refuses a stdio server with no command", () => {
    expect(preScanMcpServer({ id: "s", transport: "stdio", tools: [] })).toMatchObject({ ok: false })
  })

  it("requires https for non-loopback remote servers", () => {
    expect(
      preScanMcpServer({ id: "r", transport: "http", url: "http://api.example.com", tools: [] }),
    ).toMatchObject({ ok: false })
    expect(
      preScanMcpServer({ id: "r", transport: "http", url: "https://api.example.com", tools: [] }),
    ).toEqual({ ok: true })
    expect(
      preScanMcpServer({ id: "r", transport: "sse", url: "http://localhost:8080/sse", tools: [] }),
    ).toEqual({ ok: true })
  })

  it("rejects url+command ambiguity and missing remote url", () => {
    expect(
      preScanMcpServer({ id: "r", transport: "sse", url: "https://x.test", command: "node", tools: [] }),
    ).toMatchObject({ ok: false })
    expect(preScanMcpServer({ id: "r", transport: "http", tools: [] })).toMatchObject({ ok: false })
  })

  it("fails closed on the first bad server in a manifest", () => {
    const parsed = parseMcpManifest({
      version: 1,
      servers: [
        { id: "good", transport: "stdio", command: "node", tools: [] },
        { id: "bad", transport: "http", url: "http://plain.example.com", tools: [] },
      ],
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(preScanMcpManifest(parsed.value)).toMatchObject({ ok: false })
  })
})
