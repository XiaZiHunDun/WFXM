// domain/tools/types.ts
// 工具域 ADT — 工具定义、调用、结果、错误

// ─── 品牌类型 ───────────────────────────────────────────
export type ToolId = string & { readonly __brand: "ToolId" }

// ─── JSON Schema（简化） ────────────────────────────────
export type JSONSchema = {
  readonly type: string
  readonly properties?: Record<string, JSONSchema>
  readonly required?: readonly string[]
  readonly description?: string
}

// ─── 工具定义 ───────────────────────────────────────────
export type Tool = {
  readonly id: ToolId
  readonly name: string
  readonly description: string
  readonly inputSchema: JSONSchema
  readonly outputSchema: JSONSchema
  readonly isGenerated?: boolean
  readonly category: "read" | "write" | "execute" | "delegate"
}

// ─── 工具调用 ───────────────────────────────────────────
export type ToolCall = {
  readonly id: string
  readonly toolId: ToolId
  readonly input: Record<string, unknown>
  readonly traceId: string
}

// ─── 工具结果 ───────────────────────────────────────────
export type ToolResult = {
  readonly toolCallId: string
  readonly success: boolean
  readonly output: unknown
  readonly error?: ToolError
  readonly durationMs: number
}

// ─── 工具错误 ───────────────────────────────────────────
export type ToolError = {
  readonly _tag: string
  readonly message: string
  readonly fixSuggestion?: string
}

// ─── MCP 工具发现 ───────────────────────────────────────
export type DiscoveredTool = {
  readonly name: string
  readonly source: "mcp" | "local" | "delegate"
  readonly mcpServer?: string
}

// ─── R2.2 规范模型 ──────────────────────────────────────
// 工具名品牌类型（与 ToolId 并存；ToolName 用于按名称寻址的纯函数）
export type ToolName = string & { readonly __brand: "ToolName" }

// 风险等级
export type RiskLevel = "low" | "medium" | "high"

// 命令规格（用于 describeCommandSpec / WorkflowStep 共享）
export interface CommandSpec {
  readonly executable: string
  readonly args: readonly string[]
  readonly cwd: string
  readonly timeoutMs: number
  readonly network: "none" | "allowlist"
}

// 工具定义（spec §6.1 模型输出边界）
export interface ToolDefinition {
  readonly name: ToolName
  readonly parameters: Record<string, unknown>
  readonly result: Record<string, unknown>
  readonly risk: RiskLevel
}
