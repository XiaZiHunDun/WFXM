import { describe, expect, it } from "vitest"
import { buildWechatAllowedToolNames, WECHAT_CORE_TOOL_NAMES, WECHAT_SUBAGENT_TOOL_NAME } from "./wechat-tools.js"

describe("wechat tool allowlist", () => {
  it("merges core tools with project mcpTools", () => {
    const allowed = buildWechatAllowedToolNames({
      config: {
        version: 1,
        projects: {
          wechat: { mcpTools: ["mcp_firecrawl_firecrawl_scrape", "mcp_missing_tool"] },
        },
      },
      projectId: "wechat",
      availableMcpCapabilities: [
        "mcp_firecrawl_firecrawl_scrape",
        "mcp_todoist_lst-projects",
      ],
    })
    expect(allowed).toEqual([
      ...WECHAT_CORE_TOOL_NAMES,
      "mcp_firecrawl_firecrawl_scrape",
    ])
  })

  it("supports mcpTools wildcard", () => {
    const allowed = buildWechatAllowedToolNames({
      config: {
        version: 1,
        projects: { wechat: { mcpTools: "*" } },
      },
      projectId: "wechat",
      availableMcpCapabilities: ["mcp_a_tool", "mcp_b_tool"],
    })
    expect(allowed).toEqual([...WECHAT_CORE_TOOL_NAMES, "mcp_a_tool", "mcp_b_tool"])
  })

  it("falls back to default project entry", () => {
    const allowed = buildWechatAllowedToolNames({
      config: {
        version: 1,
        default: { mcpTools: ["mcp_todoist_lst-projects"] },
        projects: { wechat: { mcpTools: ["mcp_firecrawl_firecrawl_scrape"] } },
      },
      projectId: "unknown-project",
      availableMcpCapabilities: ["mcp_todoist_lst-projects"],
    })
    expect(allowed).toEqual([...WECHAT_CORE_TOOL_NAMES, "mcp_todoist_lst-projects"])
  })
})

describe("wechat tool allowlist edge branches", () => {
  it("appends the subagent tool when includeSubagent is set", () => {
    const allowed = buildWechatAllowedToolNames({
      config: { version: 1, projects: { wechat: { mcpTools: [] } } },
      projectId: "wechat",
      availableMcpCapabilities: [],
      includeSubagent: true,
    })
    expect(allowed).toEqual([...WECHAT_CORE_TOOL_NAMES, WECHAT_SUBAGENT_TOOL_NAME])
  })

  it("skips the project lookup for a blank project id and uses default", () => {
    const allowed = buildWechatAllowedToolNames({
      config: {
        version: 1,
        default: { mcpTools: ["mcp_d_tool"] },
        projects: { wechat: { mcpTools: ["mcp_firecrawl_firecrawl_scrape"] } },
      },
      projectId: "   ",
      availableMcpCapabilities: ["mcp_d_tool"],
    })
    expect(allowed).toEqual([...WECHAT_CORE_TOOL_NAMES, "mcp_d_tool"])
  })

  it("falls back to empty mcpTools when neither project nor default matches", () => {
    const allowed = buildWechatAllowedToolNames({
      config: { version: 1 },
      projectId: "missing",
      availableMcpCapabilities: ["mcp_d_tool"],
    })
    expect(allowed).toEqual([...WECHAT_CORE_TOOL_NAMES])
  })
})
