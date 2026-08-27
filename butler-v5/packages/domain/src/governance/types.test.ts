import { describe, expect, it } from "vitest"
import {
  buildScopedGrantScopeFromPending,
  decidePolicy,
  grantMatchesAction,
  type ActionRequest,
  type PermissionPolicy,
  type ScopedGrantRecord,
} from "./types.js"

const policy: PermissionPolicy = {
  ownerSubject: "owner-1",
  alwaysConfirm: ["send_wechat_file", "run_command", "write_file"],
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

  it("asks for run_command without grant", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "run_command",
        resource: "ls -la",
        risk: "high",
      },
      policy,
      1000,
      null,
    )
    expect(decision._tag).toBe("Ask")
  })

  it("denies high-risk write actions without grant when not alwaysConfirm", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "write",
        capability: "delete_repo",
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

  it("allows low-risk owner mcp when mcpReadonlyAutoAllow is set", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "mcp_todoist_lst_projects",
        risk: "low",
        digest: "mcp-lst",
      },
      { ...policy, mcpReadonlyAutoAllow: true },
      1000,
      null,
    )
    expect(decision).toEqual({ _tag: "Allow" })
  })

  it("asks for low-risk mcp from non-owner even with mcpReadonlyAutoAllow", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "mcp_todoist_lst_projects",
        subject: "other-user",
        risk: "low",
        digest: "mcp-lst",
      },
      { ...policy, mcpReadonlyAutoAllow: true },
      1000,
      null,
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

  it("asks when mcp grant scope tool does not match capability", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "mcp_search",
        risk: "high",
        digest: "mcp-search",
      },
      policy,
      1000,
      grant({
        scope: {
          capabilities: ["mcp_search"],
          digest: "mcp-search",
          network: "allow",
          mcp: { serverId: "demo", toolName: "fetch" },
        },
      }),
    )
    expect(decision._tag).toBe("Ask")
  })

  it("allows mcp when grant scope matches server and tool", () => {
    const decision = decidePolicy(
      {
        ...baseRequest,
        kind: "command",
        capability: "mcp_search",
        risk: "high",
        digest: "mcp-search",
      },
      policy,
      1000,
      grant({
        scope: {
          capabilities: ["mcp_search"],
          digest: "mcp-search",
          network: "allow",
          mcp: { serverId: "demo", toolName: "search" },
        },
      }),
    )
    expect(decision._tag).toBe("Allow")
  })
})

describe("buildScopedGrantScopeFromPending", () => {
  it("parses multi-server MCP capability with serverId prefix", () => {
    const scope = buildScopedGrantScopeFromPending({
      capability: "mcp_firecrawl_firecrawl_scrape",
      resource: "mcp_firecrawl_firecrawl_scrape",
      digest: "d-fc",
      mcpServerId: "firecrawl",
    })
    expect(scope.mcp).toEqual({ serverId: "firecrawl", toolName: "firecrawl_scrape" })
    expect(
      grantMatchesAction(
        grant({ scope: { ...scope, network: "allow" } }),
        {
          kind: "command",
          capability: "mcp_firecrawl_firecrawl_scrape",
          subject: "owner-1",
          resource: "mcp_firecrawl_firecrawl_scrape",
          risk: "high",
          digest: "d-fc",
          payload: {},
        },
      ),
    ).toBe(true)
  })
})
