/**
 * R8.x.10 — capability execution guard.
 *
 * R8.x.9 closed the *declaration* allowlist (`ALLOWED_CAPABILITIES` at
 * enqueue). This module is the *use* gate: given a granted capability
 * set, decide which LLM tools to advertise and which tool_calls the
 * child is actually allowed to execute.
 *
 * `general` is language-only — it never unlocks a tool.
 */
import type { LLMTool } from "@butler/adapters"
import { WEIBUTLER_LLM_TOOLS } from "./tools.js"

/**
 * Names that are language-role markers, not executable tools.
 */
const NON_EXECUTABLE = new Set<string>(["general"])

/**
 * Flatten an outbox `capabilities` payload into tool-name strings.
 * `delegate()` stores `{ tool: string }[]`; the R8.x.9 tests also
 * enqueue raw `string[]`. Both shapes must produce the same grant set
 * or the worker would silently drop every real delegation to `[]`.
 */
export function normalizeCapabilityNames(raw: unknown): readonly string[] {
  if (!Array.isArray(raw)) return []
  const names: string[] = []
  for (const entry of raw) {
    if (typeof entry === "string" && entry.length > 0) {
      names.push(entry)
      continue
    }
    if (entry !== null && typeof entry === "object" && "tool" in entry) {
      const tool = (entry as { tool: unknown }).tool
      if (typeof tool === "string" && tool.length > 0) names.push(tool)
    }
  }
  return names
}

/**
 * Capability names that correspond to a real tool the child may run.
 * `general` is stripped.
 */
export function executableCapabilities(caps: readonly string[]): readonly string[] {
  return caps.filter((c) => !NON_EXECUTABLE.has(c))
}

/**
 * True iff the child was granted `toolName` as an executable capability.
 */
export function isToolCallAllowed(toolName: string, caps: readonly string[]): boolean {
  return executableCapabilities(caps).includes(toolName)
}

/**
 * LLM tool descriptors advertised to the child. Only names that both
 * (a) are granted and (b) exist on the parent wechat tool list.
 * `delegate_to_subagent` is never granted via ALLOWED_CAPABILITIES, so
 * children cannot recurse.
 */
export function llmToolsForCapabilities(caps: readonly string[]): readonly LLMTool[] {
  const allowed = new Set(executableCapabilities(caps))
  return WEIBUTLER_LLM_TOOLS.filter((t) => allowed.has(t.name))
}
