import { describe, expect, it } from "vitest"
import { parseProjectKnowledgeSourcesJson } from "@butler/domain/knowledge/project-knowledge-sources.js"
import {
  isProjectKnowledgeWatchEnabled,
  parseProjectKnowledgeWatchConfig,
} from "./project-knowledge-sources-config.js"

describe("project-knowledge-sources-config", () => {
  it("parses watch config as opt-in", () => {
    expect(isProjectKnowledgeWatchEnabled({})).toBe(false)
    expect(isProjectKnowledgeWatchEnabled({ BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1" })).toBe(true)
    const cfg = parseProjectKnowledgeWatchConfig({
      BUTLER_V5_PROJECT_KNOWLEDGE_WATCH: "1",
      BUTLER_V5_PROJECT_KNOWLEDGE_WATCH_MS: "120000",
    })
    expect(cfg.enabled).toBe(true)
    expect(cfg.tickMs).toBe(120_000)
  })
})

// re-export parse test through config module usage
describe("parseProjectKnowledgeSourcesJson via config path", () => {
  it("accepts minimal manifest", () => {
    const parsed = parseProjectKnowledgeSourcesJson(
      JSON.stringify({ version: 1, projects: { WFXM: { globs: ["a.md"] } } }),
    )
    expect(parsed.ok).toBe(true)
  })
})
