import { describe, expect, it } from "vitest"
import { decidePolicy, type ActionRequest, type PermissionPolicy } from "./types.js"

const policy: PermissionPolicy = {
  ownerSubject: "owner-1",
  alwaysConfirm: ["send_wechat_file"],
  denyByDefault: ["write", "command", "outbound"],
}

const baseRequest: ActionRequest = {
  kind: "read",
  capability: "read_file",
  subject: "owner-1",
  resource: "README.md",
  risk: "low",
  digest: "d1",
  payload: {},
}

describe("decidePolicy", () => {
  it("allows low-risk owner reads", () => {
    expect(decidePolicy(baseRequest, policy, 1, null)).toEqual({ _tag: "Allow" })
  })

  it("asks for always-confirm capabilities", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "outbound",
        capability: "send_wechat_file",
        risk: "high",
      },
      policy,
      1000,
      null,
    )
    expect(decision._tag).toBe("Ask")
  })

  it("allows always-confirm capabilities when a matching grant is active", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "outbound",
        capability: "send_wechat_file",
        risk: "medium",
      },
      policy,
      1000,
      {
        id: "grant-1",
        runId: "run-1",
        subject: "owner-1",
        scope: { capabilities: ["send_wechat_file"] },
        remainingUses: 1,
        expiresAtMs: 2000,
        createdAtMs: 0,
      },
    )
    expect(decision).toEqual({ _tag: "Allow" })
  })

  it("denies high-risk actions without grant", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "run_command",
        risk: "high",
      },
      policy,
      1000,
      null,
    )
    expect(decision).toEqual({
      _tag: "Deny",
      reason: "high-risk action without active grant",
    })
  })
})
