import { describe, expect, it } from "vitest"
import { isLoopbackAddress, ownerAuthorizedFromAddress } from "./owner-auth.js"

describe("owner-auth", () => {
  it("accepts loopback addresses", () => {
    expect(isLoopbackAddress("127.0.0.1")).toBe(true)
    expect(isLoopbackAddress("::1")).toBe(true)
    expect(isLoopbackAddress("::ffff:127.0.0.1")).toBe(true)
  })

  it("rejects non-loopback addresses", () => {
    expect(isLoopbackAddress("192.168.1.10")).toBe(false)
    expect(isLoopbackAddress("10.0.0.5")).toBe(false)
    expect(isLoopbackAddress(undefined)).toBe(false)
  })

  it("allows vitest when remote address is unknown", () => {
    expect(ownerAuthorizedFromAddress(undefined)).toBe(true)
  })

  it("rejects non-loopback remote clients", () => {
    expect(ownerAuthorizedFromAddress("192.168.1.10")).toBe(false)
  })
})
