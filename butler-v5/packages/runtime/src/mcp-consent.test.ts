import { describe, expect, it } from "vitest"
import {
  assertMcpServerConsented,
  isMcpServerConsented,
  loadMcpManifestFromJson,
  manifestAllowsServer,
  mcpKnownServerIds,
  mcpRequireConsent,
  mcpServerIdForCapability,
  mcpServerIdFromEnv,
  parseMcpConsentServers,
} from "./mcp-consent.js"

describe("MCP consent", () => {
  describe("mcpRequireConsent", () => {
    it("defaults to off", () => {
      expect(mcpRequireConsent({})).toBe(false)
    })

    it("accepts truthy spellings (1/true/yes/on, case & whitespace insensitive)", () => {
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "1" })).toBe(true)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: " TRUE " })).toBe(true)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "yes" })).toBe(true)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "on" })).toBe(true)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "0" })).toBe(false)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "off" })).toBe(false)
      expect(mcpRequireConsent({ BUTLER_V5_MCP_REQUIRE_CONSENT: "" })).toBe(false)
    })
  })

  describe("parseMcpConsentServers", () => {
    it("parses comma/space-separated list, trims and dedupes", () => {
      expect(parseMcpConsentServers({ BUTLER_V5_MCP_CONSENT: "a, b  c, a" })).toEqual(
        new Set(["a", "b", "c"]),
      )
    })

    it("returns an empty set for empty or whitespace input", () => {
      expect(parseMcpConsentServers({})).toEqual(new Set())
      expect(parseMcpConsentServers({ BUTLER_V5_MCP_CONSENT: "   " })).toEqual(new Set())
    })
  })

  describe("mcpServerIdFromEnv", () => {
    it("prefers the explicit server id over URL/command", () => {
      expect(
        mcpServerIdFromEnv({
          BUTLER_V5_MCP_SERVER_ID: "my-server",
          BUTLER_V5_MCP_URL: "https://tools.example.com/mcp",
        }),
      ).toBe("my-server")
    })

    it("derives the hostname from a valid URL", () => {
      expect(mcpServerIdFromEnv({ BUTLER_V5_MCP_URL: "https://tools.example.com/mcp" })).toBe(
        "tools.example.com",
      )
    })

    it("falls back to mcp-http on an unparseable URL", () => {
      expect(mcpServerIdFromEnv({ BUTLER_V5_MCP_URL: "not a url" })).toBe("mcp-http")
    })

    it("uses the command basename for stdio servers", () => {
      expect(mcpServerIdFromEnv({ BUTLER_V5_MCP_COMMAND: "/usr/bin/npx" })).toBe("npx")
      expect(mcpServerIdFromEnv({ BUTLER_V5_MCP_COMMAND: "C:\\tools\\server.exe" })).toBe("server.exe")
    })

    it("falls back to mcp-default", () => {
      expect(mcpServerIdFromEnv({})).toBe("mcp-default")
    })
  })

  describe("isMcpServerConsented / assertMcpServerConsented", () => {
    it("always consents when consent is not required", () => {
      expect(isMcpServerConsented("anything", {})).toBe(true)
      expect(assertMcpServerConsented("anything", {})).toEqual({ ok: true })
    })

    it("consents only listed servers (id trimmed) when required", () => {
      const required = { BUTLER_V5_MCP_REQUIRE_CONSENT: "1", BUTLER_V5_MCP_CONSENT: "local" }
      expect(isMcpServerConsented("local", required)).toBe(true)
      expect(isMcpServerConsented(" local ", required)).toBe(true)
      expect(isMcpServerConsented("remote", required)).toBe(false)
      expect(assertMcpServerConsented("remote", required)).toMatchObject({
        ok: false,
        reason: expect.stringContaining("remote"),
      })
    })
  })

  describe("loadMcpManifestFromJson / manifestAllowsServer", () => {
    it("rejects invalid JSON", () => {
      expect(loadMcpManifestFromJson("{ not json")).toMatchObject({
        ok: false,
        reason: expect.stringContaining("JSON"),
      })
    })

    it("rejects well-formed JSON that is not a valid manifest", () => {
      expect(loadMcpManifestFromJson(JSON.stringify({ version: 1 }))).toMatchObject({ ok: false })
    })

    it("loads a valid manifest and matches servers after trim", () => {
      const loaded = loadMcpManifestFromJson(
        JSON.stringify({ version: 1, servers: [{ id: "local", transport: "stdio" }] }),
      )
      expect(loaded.ok).toBe(true)
      if (loaded.ok) {
        expect(manifestAllowsServer(loaded.manifest, "local")).toBe(true)
        expect(manifestAllowsServer(loaded.manifest, " local ")).toBe(true)
        expect(manifestAllowsServer(loaded.manifest, "other")).toBe(false)
      }
    })
  })

  describe("mcpKnownServerIds / mcpServerIdForCapability", () => {
    it("prefers the consent list, then the explicit server id, else empty", () => {
      expect(mcpKnownServerIds({ BUTLER_V5_MCP_CONSENT: "a, b" })).toEqual(["a", "b"])
      expect(mcpKnownServerIds({ BUTLER_V5_MCP_SERVER_ID: "solo" })).toEqual(["solo"])
      expect(mcpKnownServerIds({})).toEqual([])
    })

    it("returns undefined for non-mcp_ capabilities", () => {
      expect(mcpServerIdForCapability("read_file", {})).toBeUndefined()
    })

    it("resolves the server id from capability against known ids", () => {
      const env = { BUTLER_V5_MCP_SERVER_ID: "github" }
      expect(mcpServerIdForCapability("mcp_github_read", env)).toBe("github")
    })

    it("falls back to env-derived id when the capability cannot be resolved", () => {
      expect(
        mcpServerIdForCapability("mcp_unknown_read", {
          BUTLER_V5_MCP_URL: "https://tools.example.com/mcp",
        }),
      ).toBe("tools.example.com")
    })
  })
})
