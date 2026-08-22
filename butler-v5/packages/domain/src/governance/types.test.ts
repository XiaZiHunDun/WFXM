import { describe, expect, it } from "vitest"
import {
  decidePolicy,
  grantMatchesAction,
  type ActionRequest,
  type PermissionPolicy,
  type ScopedGrantRecord,
} from "./types.js"

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

function grant(
  partial: Partial<ScopedGrantRecord> & Pick<ScopedGrantRecord, "scope">,
): ScopedGrantRecord {
  return {
    id: "grant-1",
    runId: "run-1",
    subject: "owner-1",
    remainingUses: 1,
    expiresAtMs: 2000,
    createdAtMs: 0,
    delegable: false,
    approvalId: null,
    sandboxProfile: null,
    networkAllowlist: null,
    ...partial,
  }
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
      grant({
        scope: {
          capabilities: ["send_wechat_file"],
          network: "allow",
          networkHosts: ["novac2c.cdn.weixin.qq.com"],
        },
      }),
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

  it("denies always-confirm when grant path does not match", () => {
    const request: ActionRequest = {
      ...baseRequest,
      kind: "outbound",
      capability: "send_wechat_file",
      resource: "other.png",
      risk: "medium",
      digest: "send_wechat_file:other.png:{}",
    }
    expect(
      grantMatchesAction(
        grant({
          scope: {
            capabilities: ["send_wechat_file"],
            paths: ["approved.png"],
            digest: "send_wechat_file:approved.png:{}",
          },
        }),
        request,
      ),
    ).toBe(false)
    const decision = decidePolicy(
      request,
      policy,
      1000,
      grant({
        scope: {
          capabilities: ["send_wechat_file"],
          paths: ["approved.png"],
          digest: "send_wechat_file:approved.png:{}",
        },
      }),
    )
    expect(decision._tag).toBe("Ask")
  })

  it("denies always-confirm when grant digest does not match", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "outbound",
        capability: "send_wechat_file",
        resource: "file.png",
        risk: "medium",
        digest: 'send_wechat_file:file.png:{"path":"file.png"}',
      },
      policy,
      1000,
      grant({
        scope: {
          capabilities: ["send_wechat_file"],
          paths: ["file.png"],
          digest: 'send_wechat_file:file.png:{"path":"other.png"}',
        },
      }),
    )
    expect(decision._tag).toBe("Ask")
  })

  it("denies always-confirm when grant lacks network allow", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "outbound",
        capability: "send_wechat_file",
        resource: "file.png",
        risk: "medium",
        digest: "d-send",
      },
      policy,
      1000,
      grant({
        scope: {
          capabilities: ["send_wechat_file"],
          paths: ["file.png"],
          digest: "d-send",
        },
      }),
    )
    expect(decision._tag).toBe("Ask")
  })

  it("asks for mcp capabilities when no grant", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "mcp_search",
        risk: "high",
        digest: "mcp",
      },
      policy,
      1000,
      null,
    )
    expect(decision._tag).toBe("Ask")
  })
})
