import { describe, expect, it } from "vitest"
import {
  parseSandboxProfileName,
  sandboxProfileForApprovedCapability,
  SANDBOX_PROFILE_NETWORK_ALLOW,
  SANDBOX_PROFILE_NETWORK_ALLOWLIST,
  SANDBOX_PROFILE_NETWORK_DENY,
} from "./profiles.js"
import {
  currentNetworkAllowlist,
  currentSandboxProfileName,
  runWithSideEffectContext,
} from "./side-effect-context.js"

describe("sandbox profiles", () => {
  it("parses known profile names", () => {
    expect(parseSandboxProfileName("workspace-write-network-allow")).toBe(
      SANDBOX_PROFILE_NETWORK_ALLOW,
    )
    expect(parseSandboxProfileName("workspace-write-network-allowlist")).toBe(
      SANDBOX_PROFILE_NETWORK_ALLOWLIST,
    )
    expect(parseSandboxProfileName("nope")).toBeNull()
  })

  it("binds deny ceiling for run_command / mcp on approve", () => {
    expect(sandboxProfileForApprovedCapability("run_command")).toBe(SANDBOX_PROFILE_NETWORK_DENY)
    expect(sandboxProfileForApprovedCapability("mcp_search")).toBe(SANDBOX_PROFILE_NETWORK_DENY)
    expect(sandboxProfileForApprovedCapability("send_wechat_file")).toBeNull()
  })

  it("elevates to network-allow when requested", () => {
    expect(sandboxProfileForApprovedCapability("run_command", { elevateNetwork: true })).toBe(
      SANDBOX_PROFILE_NETWORK_ALLOW,
    )
  })

  it("selects allowlist profile when networkAllowlist provided", () => {
    expect(
      sandboxProfileForApprovedCapability("run_command", {
        networkAllowlist: ["registry.npmjs.org:443"],
      }),
    ).toBe(SANDBOX_PROFILE_NETWORK_ALLOWLIST)
  })
})

describe("side-effect context", () => {
  it("exposes sandboxProfile and networkAllowlist inside runWithSideEffectContext", async () => {
    let profile: string | null = null
    let allowlist: readonly string[] | null = null
    await runWithSideEffectContext(
      {
        sandboxProfile: SANDBOX_PROFILE_NETWORK_ALLOWLIST,
        networkAllowlist: ["registry.npmjs.org:443"],
        grantId: "g1",
        capability: "run_command",
      },
      async () => {
        profile = currentSandboxProfileName()
        allowlist = currentNetworkAllowlist()
      },
    )
    expect(profile).toBe(SANDBOX_PROFILE_NETWORK_ALLOWLIST)
    expect(allowlist).toEqual(["registry.npmjs.org:443"])
  })

  it("clears ALS after runWithSideEffectContext", async () => {
    expect(currentSandboxProfileName()).toBeNull()
    const seen = await runWithSideEffectContext(
      {
        sandboxProfile: SANDBOX_PROFILE_NETWORK_ALLOW,
        networkAllowlist: null,
        grantId: "g1",
        capability: "run_command",
      },
      async () => currentSandboxProfileName(),
    )
    expect(seen).toBe(SANDBOX_PROFILE_NETWORK_ALLOW)
    expect(currentSandboxProfileName()).toBeNull()
  })
})
