// domain/tools/pure.ts
// 工具域纯函数 — 工具分类、校验、安全级别判定

import type { Tool, ToolCall, ToolResult, ToolError } from "./types.js"

// ─── 工具分类判定 [OPT-4] ───────────────────────────────
export function classifyTool(name: string): Tool["category"] {
  const readTools = ["read_file", "grep", "glob", "ls", "read", "search"]
  const writeTools = ["write_file", "edit", "write", "delete_file", "delete"]
  const executeTools = ["execute_command", "run", "test", "build", "typecheck"]
  const delegateTools = ["delegate_task", "delegate", "run_workflow"]

  if (readTools.some((t) => name.startsWith(t) || name.includes(t))) return "read"
  if (writeTools.some((t) => name.startsWith(t) || name.includes(t))) return "write"
  if (executeTools.some((t) => name.startsWith(t) || name.includes(t))) return "execute"
  if (delegateTools.some((t) => name.startsWith(t) || name.includes(t))) return "delegate"
  return "read"
}

// ─── 工具调用校验 ───────────────────────────────────────
export function validateToolCall(
  call: ToolCall,
  tool: Tool,
): { valid: boolean; error?: ToolError } {
  if (call.toolId !== tool.id) {
    return {
      valid: false,
      error: { _tag: "InvalidToolId", message: `Tool ID mismatch: ${call.toolId} vs ${tool.id}` },
    }
  }
  if (tool.inputSchema.required) {
    for (const key of tool.inputSchema.required) {
      if (!(key in call.input)) {
        return {
          valid: false,
          error: { _tag: "MissingRequiredInput", message: `Missing required input: ${key}` },
        }
      }
    }
  }
  return { valid: true }
}

// ─── 工具结果评估 ───────────────────────────────────────
export function evaluateToolResult(result: ToolResult): {
  summary: string
  isSuccess: boolean
  duration: number
} {
  return {
    summary: result.success
      ? `工具 ${result.toolCallId} 执行成功`
      : `工具 ${result.toolCallId} 执行失败: ${result.error?.message ?? "unknown"}`,
    isSuccess: result.success,
    duration: result.durationMs,
  }
}

// ─── 工具超时判断 ───────────────────────────────────────
export function isToolTimeout(durationMs: number, timeoutMs: number = 60_000): boolean {
  return durationMs > timeoutMs
}

// ─── 工具批量排序（按优先级） ────────────────────────────
export function sortToolsByPriority(tools: readonly Tool[]): readonly Tool[] {
  const priority: Record<Tool["category"], number> = {
    read: 1,
    write: 2,
    execute: 3,
    delegate: 4,
  }
  return [...tools].sort((a, b) => (priority[a.category] ?? 5) - (priority[b.category] ?? 5))
}

// ─── R2.2 规范模型纯函数 ────────────────────────────────
import type { CommandSpec, ToolDefinition } from "./types.js"

// 禁止出现在可执行文件名 / 参数中的 shell 元字符
const FORBIDDEN_SHELL = /[;&|`$<>(){}[\]\\\n]/

// 工具定义校验（返回 ok/reason，不使用 throw [NEW-OPT-21]）
export function validateToolDefinition(def: ToolDefinition): { ok: boolean; reason?: string } {
  if (def.name === "") {
    return { ok: false, reason: "工具名不能为空" }
  }
  if (!def.parameters || !def.result) {
    return { ok: false, reason: "parameters 与 result 必填" }
  }
  if (def.risk === "high") {
    return { ok: false, reason: "high 风险工具不允许通过纯函数校验" }
  }
  return { ok: true }
}

// 命令规格描述器：剔除 shell 元字符路径，返回 ok/reason 或描述体
export function describeCommandSpec(spec: CommandSpec): {
  ok: boolean
  executable: string
  args: readonly string[]
  timeoutMs: number
  network: CommandSpec["network"]
  reason?: string
} {
  if (FORBIDDEN_SHELL.test(spec.executable)) {
    return {
      ok: false,
      executable: spec.executable,
      args: spec.args,
      timeoutMs: spec.timeoutMs,
      network: spec.network,
      reason: "executable contains shell metacharacter",
    }
  }
  for (const a of spec.args) {
    if (FORBIDDEN_SHELL.test(a)) {
      return {
        ok: false,
        executable: spec.executable,
        args: spec.args,
        timeoutMs: spec.timeoutMs,
        network: spec.network,
        reason: `arg contains shell metacharacter: ${a}`,
      }
    }
  }
  return {
    ok: true,
    executable: spec.executable,
    args: spec.args,
    timeoutMs: spec.timeoutMs,
    network: spec.network,
  }
}
