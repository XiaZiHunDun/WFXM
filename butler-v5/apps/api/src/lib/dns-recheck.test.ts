import { describe, expect, it, vi } from "vitest"
import { lookup } from "node:dns/promises"
import type dnsPromises from "node:dns/promises"
import { assertPublicHost, makeGuardedFetch } from "./dns-recheck.js"

vi.mock("node:dns/promises", async () => {
  const actual = await vi.importActual<typeof dnsPromises>("node:dns/promises")
  return {
    ...actual,
    lookup: vi.fn(),
  }
})

const mockLookup = vi.mocked(lookup)

describe("assertPublicHost (D73 SEC-002 DNS rebinding defense)", () => {
  it("passes for literal IPv4 that is public", async () => {
    await expect(assertPublicHost("http://8.8.8.8/foo", () => false)).resolves.toBeUndefined()
    expect(mockLookup).not.toHaveBeenCalled()
  })

  it("rejects a literal IPv4 that the blocklist rejects (no DNS lookup)", async () => {
    await expect(
      assertPublicHost("http://127.0.0.1:8080/foo", (h) => h === "127.0.0.1"),
    ).rejects.toThrow(/blocked range|private-network deny list/)
    expect(mockLookup).not.toHaveBeenCalled()
  })

  it("rejects when DNS resolves to a blocked address", async () => {
    mockLookup.mockResolvedValueOnce([
      { address: "10.0.0.5", family: 4 },
      { address: "8.8.8.8", family: 4 },
    ] as never)
    await expect(
      assertPublicHost("https://attacker.example.com/foo", (h) => h.startsWith("10.")),
    ).rejects.toThrow(/resolves to 10\.0\.0\.5/)
  })

  it("passes when all resolved addresses pass", async () => {
    mockLookup.mockResolvedValueOnce([
      { address: "8.8.8.8", family: 4 },
      { address: "1.1.1.1", family: 4 },
    ] as never)
    await expect(
      assertPublicHost("https://dns.example.com/foo", () => false),
    ).resolves.toBeUndefined()
  })

  it("rejects when DNS lookup throws", async () => {
    mockLookup.mockRejectedValueOnce(new Error("ENOTFOUND"))
    await expect(
      assertPublicHost("https://nope.example.com/foo", () => false),
    ).rejects.toThrow(/lookup failed/)
  })

  it("rejects when DNS returns zero addresses", async () => {
    mockLookup.mockResolvedValueOnce([] as never)
    await expect(
      assertPublicHost("https://empty.example.com/foo", () => false),
    ).rejects.toThrow(/no addresses/)
  })
})

describe("makeGuardedFetch (D73 SEC-002 wrapper)", () => {
  it("invokes the wrapped fetch after asserting the host is public", async () => {
    mockLookup.mockResolvedValueOnce([{ address: "8.8.8.8", family: 4 }] as never)
    const baseFetch = vi.fn(async () => new Response("ok", { status: 200 }))
    const guarded = makeGuardedFetch(
      baseFetch as unknown as typeof fetch,
      "https://api.example.com/v1",
      () => false,
    )
    const res = await guarded("https://api.example.com/v1")
    expect(res.status).toBe(200)
    expect(baseFetch).toHaveBeenCalledOnce()
  })

  it("does NOT invoke the wrapped fetch when the host fails the recheck", async () => {
    mockLookup.mockResolvedValueOnce([{ address: "169.254.169.254", family: 4 }] as never)
    const baseFetch = vi.fn(async () => new Response("ok", { status: 200 }))
    const guarded = makeGuardedFetch(
      baseFetch as unknown as typeof fetch,
      "https://metadata.example.com/v1",
      (h) => h === "169.254.169.254",
    )
    await expect(guarded("https://metadata.example.com/v1")).rejects.toThrow(
      /blocked|deny list/,
    )
    expect(baseFetch).not.toHaveBeenCalled()
  })
})