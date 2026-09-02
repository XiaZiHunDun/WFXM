import { describe, expect, it } from "vitest"
import {
  actionRequiresNetworkGrant,
  consumeGrantUse,
  grantAllowsNetworkHost,
  normalizeGrantHost,
  normalizeGrantPath,
  type ScopedGrantRecord,
} from "./types.js"

function makeGrant(overrides: Partial<ScopedGrantRecord> = {}): ScopedGrantRecord {
  return {
    id: "grant-1",
    runId: "run-1",
    subject: "owner",
    capability: "read_file",
    scope: { digest: "abc" },
    remainingUses: 3,
    expiresAtMs: 1_000_000,
    createdAtMs: 10,
    delegable: false,
    approvalId: "step-1",
    sandboxProfile: null,
    networkAllowlist: null,
    ...overrides,
  }
}

describe("consumeGrantUse", () => {
  it("decrements remainingUses by one", () => {
    expect(consumeGrantUse(makeGrant({ remainingUses: 3 })).remainingUses).toBe(2)
    expect(consumeGrantUse(makeGrant({ remainingUses: 1 })).remainingUses).toBe(0)
  })

  it("never decrements below zero", () => {
    expect(consumeGrantUse(makeGrant({ remainingUses: 0 })).remainingUses).toBe(0)
  })

  it("returns the same grant unchanged when uses are unlimited (null)", () => {
    const grant = makeGrant({ remainingUses: null })
    expect(consumeGrantUse(grant)).toBe(grant)
    expect(consumeGrantUse(grant).remainingUses).toBeNull()
  })

  it("does not mutate the input grant", () => {
    const grant = makeGrant({ remainingUses: 2 })
    consumeGrantUse(grant)
    expect(grant.remainingUses).toBe(2)
  })
})

describe("normalizeGrantPath", () => {
  it("trims surrounding whitespace", () => {
    expect(normalizeGrantPath("  /data/file.txt  ")).toBe("/data/file.txt")
    expect(normalizeGrantPath("   ")).toBe("")
  })

  it("converts backslashes to forward slashes", () => {
    expect(normalizeGrantPath("C:\\dir\\file.txt")).toBe("C:/dir/file.txt")
    expect(normalizeGrantPath("a\\b\\c")).toBe("a/b/c")
  })
})

describe("normalizeGrantHost", () => {
  it("trims whitespace and lowercases", () => {
    expect(normalizeGrantHost("  API.Example.COM  ")).toBe("api.example.com")
    expect(normalizeGrantHost(" Host-1 ")).toBe("host-1")
  })
})

describe("actionRequiresNetworkGrant", () => {
  it("requires network grant for outbound actions", () => {
    expect(actionRequiresNetworkGrant("outbound", "send_wechat_file")).toBe(true)
  })

  it("requires network grant for MCP capabilities regardless of kind", () => {
    expect(actionRequiresNetworkGrant("read", "mcp_serverid_tool")).toBe(true)
    expect(actionRequiresNetworkGrant("command", "mcp_serverid_tool")).toBe(true)
  })

  it("does not require a network grant for local read/write/command primitives", () => {
    expect(actionRequiresNetworkGrant("read", "read_file")).toBe(false)
    expect(actionRequiresNetworkGrant("write", "write_file")).toBe(false)
    expect(actionRequiresNetworkGrant("command", "run_command")).toBe(false)
  })
})

describe("grantAllowsNetworkHost", () => {
  it("denies everything when the grant scope does not allow the network", () => {
    expect(
      grantAllowsNetworkHost(makeGrant({ scope: { digest: "a", network: "deny" } }), "api.example.com"),
    ).toBe(false)
    expect(grantAllowsNetworkHost(makeGrant({ scope: { digest: "a" } }), "api.example.com")).toBe(false)
  })

  it("allows any host when network is allowed without a host allowlist", () => {
    expect(
      grantAllowsNetworkHost(makeGrant({ scope: { digest: "a", network: "allow" } }), "any.host.com"),
    ).toBe(true)
    expect(
      grantAllowsNetworkHost(makeGrant({ scope: { digest: "a", network: "allow", networkHosts: [] } }), "any.host.com"),
    ).toBe(true)
  })

  it("allows only hosts on the allowlist (case-insensitive)", () => {
    const grant = makeGrant({
      scope: {
        digest: "a",
        network: "allow",
        networkHosts: [normalizeGrantHost("api.example.com")],
      },
    })
    expect(grantAllowsNetworkHost(grant, "api.example.com")).toBe(true)
    expect(grantAllowsNetworkHost(grant, "API.Example.COM")).toBe(true)
    expect(grantAllowsNetworkHost(grant, "other.example.com")).toBe(false)
  })
})