import { describe, expect, it } from "vitest"
import { buildWechatAllowedToolNames, WECHAT_CORE_TOOL_NAMES } from "@butler/domain/runtime.js"
import { parseWechatToolAllowlistJson } from "./wechat-tool-allowlist.js"

describe("wechat-tool-allowlist", () => {
  it("parses project mcpTools and wildcard", () => {
    const config = parseWechatToolAllowlistJson(
      JSON.stringify({
        version: 1,
        default: { mcpTools: [] },
        projects: {
          wechat: { mcpTools: ["mcp_firecrawl_firecrawl_scrape"] },
          all: { mcpTools: "*" },
        },
      }),
    )
    expect(config?.projects?.["wechat"]?.mcpTools).toEqual(["mcp_firecrawl_firecrawl_scrape"])
    expect(config?.projects?.["all"]?.mcpTools).toBe("*")
  })

  it("builds project allowlist from parsed config", () => {
    const config = parseWechatToolAllowlistJson(
      JSON.stringify({
        version: 1,
        projects: {
          wechat: {
            mcpTools: ["mcp_firecrawl_firecrawl_scrape", "mcp_todoist_lst-projects"],
          },
        },
      }),
    )
    expect(config).not.toBeNull()
    if (!config) return
    const allowed = buildWechatAllowedToolNames({
      config,
      projectId: "wechat",
      availableMcpCapabilities: [
        "mcp_firecrawl_firecrawl_scrape",
        "mcp_github_get_file_contents",
        "mcp_todoist_lst-projects",
      ],
    })
    expect(allowed).toEqual([
      ...WECHAT_CORE_TOOL_NAMES,
      "mcp_firecrawl_firecrawl_scrape",
      "mcp_todoist_lst-projects",
    ])
  })
})
