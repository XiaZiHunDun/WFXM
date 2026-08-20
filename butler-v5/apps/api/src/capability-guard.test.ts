/**
 * R8.x.10 — capability execution guard.
 *
 * R8.x.9 only filtered capability *declaration* at enqueue time. These
 * tests pin the execution-time rules: payload shape normalization,
 * which tools a child may actually run, and which LLM tool descriptors
 * are advertised to the child.
 */
import { describe, expect, it } from "vitest"
import {
  isToolCallAllowed,
  llmToolsForCapabilities,
  normalizeCapabilityNames,
} from "./capability-guard.js"

describe("capability-guard", () => {
  it("normalizeCapabilityNames reads string entries", () => {
    expect(normalizeCapabilityNames(["general", "get_current_time"])).toEqual([
      "general",
      "get_current_time",
    ])
  })

  it("normalizeCapabilityNames reads {tool} objects from delegate payload", () => {
    expect(normalizeCapabilityNames([{ tool: "get_current_time" }])).toEqual(["get_current_time"])
  })

  it("normalizeCapabilityNames drops non-string junk", () => {
    expect(normalizeCapabilityNames([1, null, { tool: 3 }, "recall_history"])).toEqual([
      "recall_history",
    ])
  })

  it("isToolCallAllowed denies tools not in the granted executable set", () => {
    expect(isToolCallAllowed("run_command", ["general", "get_current_time"])).toBe(false)
    expect(isToolCallAllowed("get_current_time", ["general", "get_current_time"])).toBe(true)
    expect(isToolCallAllowed("get_current_time", ["general"])).toBe(false)
    expect(isToolCallAllowed("general", ["general"])).toBe(false)
    expect(isToolCallAllowed("send_wechat_file", ["general", "read_file"])).toBe(false)
  })

  it("llmToolsForCapabilities omits general and advertises granted workspace tools", () => {
    const tools = llmToolsForCapabilities(["general", "get_current_time", "read_file"])
    expect(tools.map((t) => t.name)).toEqual(["get_current_time", "read_file"])
  })

  it("llmToolsForCapabilities with only general advertises no tools", () => {
    expect(llmToolsForCapabilities(["general"])).toEqual([])
  })
})
