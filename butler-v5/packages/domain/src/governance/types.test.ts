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
    capability: "read_file",
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
        capability: "send_wechat_file",
        scope: {
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

  it("P1: denies always-confirm when grant is expired (TTL mismatch)", () => {
    const request: ActionRequest = {
      ...baseRequest,
      kind: "outbound",
      capability: "send_wechat_file",
      resource: "file.png",
      risk: "medium",
      digest: "d-ttl",
    }
    const decision = decidePolicy(
      request,
      policy,
      2000,
      grant({
        capability: "send_wechat_file",
        expiresAtMs: 1999,
        scope: {
          capabilities: ["send_wechat_file"],
          paths: ["file.png"],
          digest: "d-ttl",
        },
      }),
    )
    expect(decision._tag).toBe("Ask")
  })

  it("P1: denies always-confirm when grant is exhausted (remainingUses 0)", () => {
    const request: ActionRequest = {
      ...baseRequest,
      kind: "outbound",
      capability: "send_wechat_file",
      resource: "file.png",
      risk: "medium",
      digest: "d-uses",
    }
    const decision = decidePolicy(
      request,
      policy,
      1000,
      grant({
        capability: "send_wechat_file",
        remainingUses: 0,
        scope: {
          capabilities: ["send_wechat_file"],
          paths: ["file.png"],
          digest: "d-uses",
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
        capability: "mcp_search",
        scope: {
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
        grant({ capability: "mcp_firecrawl_firecrawl_scrape", scope: { ...scope, network: "allow" } }),
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

describe("grantMatchesAction", () => {
  const req = (over: Partial<ActionRequest> = {}): ActionRequest => ({
    kind: "read",
    capability: "read_file",
    subject: "owner-1",
    resource: "a/b.txt",
    risk: "low",
    digest: "d1",
    payload: {},
    ...over,
  })

  it("rejects when capability differs", () => {
    expect(grantMatchesAction(grant({ capability: "read_file", scope: {} }), req({ capability: "write_file" }))).toBe(false)
  })

  it("rejects when the grant digest pins a different digest", () => {
    expect(grantMatchesAction(grant({ scope: { digest: "pinned" } }), req({ digest: "other" }))).toBe(false)
    expect(grantMatchesAction(grant({ scope: { digest: "d1" } }), req())).toBe(true)
  })

  it("matches resource against a path-scoped grant", () => {
    expect(grantMatchesAction(grant({ scope: { paths: ["a/b.txt"] } }), req())).toBe(true)
    expect(grantMatchesAction(grant({ scope: { paths: ["a/b.txt"] } }), req({ resource: "c/d.txt" }))).toBe(false)
  })

  it("requires network allow when the action needs outbound egress", () => {
    const outboundReq = () => req({ kind: "outbound", capability: "send_wechat_file" })
    expect(grantMatchesAction(grant({ capability: "send_wechat_file", scope: {} }), outboundReq())).toBe(false)
    expect(grantMatchesAction(grant({ capability: "send_wechat_file", scope: { network: "allow" } }), outboundReq())).toBe(true)
  })

  it("matches an unadorned grant against an identical request", () => {
    expect(grantMatchesAction(grant({ scope: {} }), req())).toBe(true)
  })
})

describe("buildScopedGrantScopeFromPending path/network normalization", () => {
  it("adds a normalized path for file capabilities and trims resource", () => {
    expect(buildScopedGrantScopeFromPending({ capability: "read_file", resource: "  a/b.txt  ", digest: "d" })).toEqual({
      digest: "d",
      paths: ["a/b.txt"],
    })
    expect(buildScopedGrantScopeFromPending({ capability: "read_file", resource: "   ", digest: "d" })).toEqual({ digest: "d" })
  })

  it("does not bind non-file capabilities to a path", () => {
    expect(buildScopedGrantScopeFromPending({ capability: "run_command", resource: "x/y.sh", digest: "d" })).toEqual({
      digest: "d",
    })
  })

  it("stamps network allow (+hosts) when forceNetworkAllow or outbound", () => {
    expect(
      buildScopedGrantScopeFromPending({
        capability: "send_wechat_file",
        resource: "",
        digest: "d",
        networkHosts: ["API.Example.COM"],
      }),
    ).toEqual({ digest: "d", network: "allow", networkHosts: ["api.example.com"] })
    expect(
      buildScopedGrantScopeFromPending({ capability: "read_file", resource: "", digest: "d", forceNetworkAllow: true }),
    ).toEqual({ digest: "d", network: "allow" })
    expect(buildScopedGrantScopeFromPending({ capability: "read_file", resource: "", digest: "d" })).toEqual({ digest: "d" })
  })
})
