import { describe, expect, it } from "vitest"
import {
  containsSecret,
  redactSecrets,
  redactSecretText,
  shouldRedactToolResults,
} from "./secret-redact.js"

describe("P2 secret redaction toolkit", () => {
  it("redacts text secrets inline", () => {
    expect(redactSecretText("key sk-abc123456789 and token=deadbeef")).toBe(
      "key *** and token=***",
    )
  })

  it("does not alter plain text", () => {
    const plain = "run git status in the workspace"
    expect(redactSecretText(plain)).toBe(plain)
  })

  it("deep-redacts secret-like keys and values", () => {
    const value = {
      outputs: ["done"],
      token: "deadbeef",
      apiKey: "123456",
      payload: { authorization: "Bearer xyz" },
    }
    const redacted = redactSecrets(value) as Record<string, unknown>
    expect(redacted.token).toBe("***")
    expect(redacted.apiKey).toBe("***")
    expect(redacted.payload).toEqual({ authorization: "***" })
  })

  it("scans nested values for secrets", () => {
    expect(containsSecret("all clear")).toBe(false)
    expect(containsSecret({ data: "ghp_1234567890123456789012" })).toBe(true)
    expect(containsSecret({ data: "hello" })).toBe(false)
  })

  it("strict-mode flag is off by default", () => {
    expect(shouldRedactToolResults()).toBe(false)
    expect(shouldRedactToolResults({ BUTLER_V5_REDACT_TOOL_RESULTS: "1" })).toBe(true)
    expect(shouldRedactToolResults({ BUTLER_V5_REDACT_TOOL_RESULTS: "true" })).toBe(true)
    expect(shouldRedactToolResults({ BUTLER_V5_REDACT_TOOL_RESULTS: "0" })).toBe(false)
  })
})