import { describe, expect, it } from "vitest"
import {
  hashNetworkAllowlistForAudit,
  isDestinationAllowedInNetworkAllowlist,
  normalizeNetworkAllowlistEntry,
  resolveSandboxEgressIsolation,
  resolveSandboxNetworkMode,
  validateNetworkAllowlist,
} from "./network-allowlist.js"

describe("network allowlist", () => {
  it("normalizes host:port and default port 443", () => {
    expect(normalizeNetworkAllowlistEntry("registry.npmjs.org:443")).toEqual({
      ok: true,
      value: "registry.npmjs.org:443",
    })
    expect(normalizeNetworkAllowlistEntry("PYPI.org")).toEqual({
      ok: true,
      value: "pypi.org:443",
    })
  })

  it("rejects wildcards and CIDR", () => {
    expect(normalizeNetworkAllowlistEntry("*").ok).toBe(false)
    expect(normalizeNetworkAllowlistEntry("0.0.0.0/0").ok).toBe(false)
  })

  it("rejects private hosts by default", () => {
    const result = validateNetworkAllowlist(["127.0.0.1:3000"])
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toMatch(/private or loopback/)
  })

  it("allows private hosts when opted in", () => {
    const result = validateNetworkAllowlist(["127.0.0.1:3000"], {
      allowPrivateEgress: true,
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.normalized).toEqual(["127.0.0.1:3000"])
  })

  it("deduplicates and caps entries", () => {
    const entries = Array.from({ length: 9 }, (_, i) => `host${i}.example.com`)
    expect(validateNetworkAllowlist(entries).ok).toBe(false)
    const dup = validateNetworkAllowlist([
      "registry.npmjs.org",
      "registry.npmjs.org:443",
    ])
    expect(dup.ok).toBe(true)
    if (dup.ok) expect(dup.normalized).toEqual(["registry.npmjs.org:443"])
  })

  it("hashes normalized list for audit", () => {
    const a = hashNetworkAllowlistForAudit(["registry.npmjs.org:443"])
    const b = hashNetworkAllowlistForAudit(["registry.npmjs.org:443"])
    expect(a).toBe(b)
    expect(a).toHaveLength(16)
  })

  it("matches destination host:port", () => {
    expect(isDestinationAllowedInNetworkAllowlist("Registry.npmjs.org", 443, [
      "registry.npmjs.org:443",
    ])).toBe(true)
    expect(isDestinationAllowedInNetworkAllowlist("evil.example", 443, ["registry.npmjs.org:443"])).toBe(
      false,
    )
  })

  it("resolveSandboxNetworkMode defaults to binary", () => {
    expect(resolveSandboxNetworkMode({})).toBe("binary")
    expect(resolveSandboxNetworkMode({ BUTLER_V5_SANDBOX_NETWORK_MODE: "allowlist" })).toBe(
      "allowlist",
    )
  })

  it("resolveSandboxEgressIsolation defaults to proxy", () => {
    expect(resolveSandboxEgressIsolation({})).toBe("proxy")
    expect(resolveSandboxEgressIsolation({ BUTLER_V5_SANDBOX_EGRESS_ISOLATION: "slirp" })).toBe(
      "slirp",
    )
  })
})
