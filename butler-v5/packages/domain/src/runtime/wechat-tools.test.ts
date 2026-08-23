import { describe, expect, it } from "vitest"
import { buildWechatAllowedToolNames, WECHAT_CORE_TOOL_NAMES } from "./wechat-tools.js"

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
