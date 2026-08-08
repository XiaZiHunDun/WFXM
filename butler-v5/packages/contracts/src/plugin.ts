import type { ToolName } from "../../domain/src/tools/types.js"

export type PluginTrust = "bundled" | "github" | "url" | "clawhub" | "marketplace" | "lobehub"

export interface PluginManifest {
  readonly name: string
  readonly version: string
  readonly trust: PluginTrust
  readonly provides: readonly ("tool" | "channel" | "guard" | "event-source")[]
  readonly tools: readonly { readonly name: ToolName; readonly risk: "low" | "medium" | "high" }[]
  readonly requiredCapabilities: readonly (
    "fs.read" | "fs.write" | "net" | "subprocess" | "memory.write" | "long-running"
  )[]
  readonly signature: string
}
