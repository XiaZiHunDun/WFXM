import { describe, expect, it } from "vitest"
import { createHostCredentialProvider, injectRunCommandCredentials } from "./host-credentials.js"

const CREDS = JSON.stringify({ REGISTRY_TOKEN: "supersecret", "bad name": "nope" })

describe("P2 host-held credential provider", () => {
  it("lists only valid names, never values", async () => {
    const p = createHostCredentialProvider({ BUTLER_V5_CREDENTIALS: CREDS })
    const names = await p.availableCredentials()
    expect(names).toEqual(["REGISTRY_TOKEN"])
    expect(JSON.stringify(names)).not.toContain("supersecret")
  })

  it("resolves requested names; fails closed on unknown/invalid", async () => {
    const p = createHostCredentialProvider({ BUTLER_V5_CREDENTIALS: CREDS })
    await expect(p.resolveCredentials(["REGISTRY_TOKEN"])).resolves.toEqual({
      REGISTRY_TOKEN: "supersecret",
    })
    await expect(p.resolveCredentials(["MISSING"])).rejects.toThrow("not resolvable")
    await expect(p.resolveCredentials(["bad name"])).rejects.toThrow("invalid credential name")
  })

  it("returns empty list when credentials unset", async () => {
    const p = createHostCredentialProvider({})
    expect(await p.availableCredentials()).toEqual([])
  })
})

describe("P2 run_command credential injection gate", () => {
  const provider = createHostCredentialProvider({ BUTLER_V5_CREDENTIALS: CREDS })

  it("no-op returns base env for empty request", async () => {
    const r = await injectRunCommandCredentials({
      provider,
      requestedNames: [],
      allowlist: [],
      baseEnv: { PATH: "/bin" },
    })
    expect(r).toEqual({ ok: true, env: { PATH: "/bin" } })
  })

  it("merges allowed credential values and drops unauthorized names (fail-closed)", async () => {
    const ok = await injectRunCommandCredentials({
      provider,
      requestedNames: ["REGISTRY_TOKEN", "NOT_ALLOWED"],
      allowlist: ["REGISTRY_TOKEN"],
      baseEnv: {},
    })
    expect(ok).toEqual({ ok: false, reason: "credential not authorized for run_command: NOT_ALLOWED" })
  })

  it("injects authorized credential value into child env", async () => {
    const r = await injectRunCommandCredentials({
      provider,
      requestedNames: ["REGISTRY_TOKEN"],
      allowlist: ["REGISTRY_TOKEN"],
      baseEnv: {},
    })
    expect(r.ok).toBe(true)
    if (r.ok) expect(r.env).toEqual({ REGISTRY_TOKEN: "supersecret" })
  })
})