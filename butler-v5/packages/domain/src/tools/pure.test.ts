import { describe, it, expect } from "vitest"
import {
  classifyTool,
  validateToolCall,
  evaluateToolResult,
  isToolTimeout,
  sortToolsByPriority,
  validateToolDefinition,
  describeCommandSpec,
} from "./pure.js"
import type { CommandSpec, Tool, ToolCall, ToolDefinition, ToolName, ToolResult } from "./types.js"

const sampleTool: Tool = {
  id: "tool-1" as Tool["id"],
  name: "read_file",
  description: "Read a file",
  inputSchema: { type: "object", properties: {}, required: [] },
  outputSchema: { type: "object" },
  category: "read",
}

const sampleToolWithRequired: Tool = {
  id: "tool-2" as Tool["id"],
  name: "write_file",
  description: "Write a file",
  inputSchema: {
    type: "object",
    properties: {},
    required: ["path", "content"],
  },
  outputSchema: { type: "object" },
  category: "write",
}

describe("tools/pure", () => {
  describe("classifyTool", () => {
    it("classifies read_file as read", () => {
      expect(classifyTool("read_file")).toBe("read")
    })
    it("classifies write_file as write", () => {
      expect(classifyTool("write_file")).toBe("write")
    })
    it("classifies execute_command as execute", () => {
      expect(classifyTool("execute_command")).toBe("execute")
    })
    it("classifies delegate_task as delegate", () => {
      expect(classifyTool("delegate_task")).toBe("delegate")
    })
    it("classifies unknown tool as read", () => {
      expect(classifyTool("unknown_tool")).toBe("read")
    })
  })

  describe("validateToolCall", () => {
    it("validates matching tool call", () => {
      const call: ToolCall = {
        id: "call-1",
        toolId: "tool-1" as ToolCall["toolId"],
        input: {},
        traceId: "trace-1",
      }
      const result = validateToolCall(call, sampleTool)
      expect(result.valid).toBe(true)
    })

    it("rejects mismatched tool ID", () => {
      const call: ToolCall = {
        id: "call-1",
        toolId: "wrong-id" as ToolCall["toolId"],
        input: {},
        traceId: "trace-1",
      }
      const result = validateToolCall(call, sampleTool)
      expect(result.valid).toBe(false)
      expect(result.error?._tag).toBe("InvalidToolId")
    })

    it("rejects missing required input", () => {
      const call: ToolCall = {
        id: "call-1",
        toolId: "tool-2" as ToolCall["toolId"],
        input: { path: "/tmp/test" },
        traceId: "trace-1",
      }
      const result = validateToolCall(call, sampleToolWithRequired)
      expect(result.valid).toBe(false)
      expect(result.error?._tag).toBe("MissingRequiredInput")
    })

    it("accepts call with all required inputs", () => {
      const call: ToolCall = {
        id: "call-1",
        toolId: "tool-2" as ToolCall["toolId"],
        input: { path: "/tmp/test", content: "hello" },
        traceId: "trace-1",
      }
      const result = validateToolCall(call, sampleToolWithRequired)
      expect(result.valid).toBe(true)
    })
  })

  describe("evaluateToolResult", () => {
    it("reports success", () => {
      const result: ToolResult = {
        toolCallId: "call-1",
        success: true,
        output: "ok",
        durationMs: 10,
      }
      const evaluation = evaluateToolResult(result)
      expect(evaluation.isSuccess).toBe(true)
      expect(evaluation.summary).toContain("成功")
    })

    it("reports failure", () => {
      const result: ToolResult = {
        toolCallId: "call-2",
        success: false,
        output: null,
        error: { _tag: "ExecutionError", message: "command not found" },
        durationMs: 100,
      }
      const evaluation = evaluateToolResult(result)
      expect(evaluation.isSuccess).toBe(false)
      expect(evaluation.summary).toContain("失败")
    })
  })

  describe("isToolTimeout", () => {
    it("returns true when duration exceeds default timeout", () => {
      expect(isToolTimeout(61_000)).toBe(true)
    })
    it("returns false when duration is within default timeout", () => {
      expect(isToolTimeout(30_000)).toBe(false)
    })
    it("respects custom timeout", () => {
      expect(isToolTimeout(5_000, 3_000)).toBe(true)
      expect(isToolTimeout(5_000, 10_000)).toBe(false)
    })
  })

  describe("sortToolsByPriority", () => {
    it("sorts tools by category priority", () => {
      const tools: readonly Tool[] = [
        { ...sampleTool, id: "t1" as Tool["id"], name: "delegate", category: "delegate" },
        { ...sampleTool, id: "t2" as Tool["id"], name: "read", category: "read" },
        { ...sampleTool, id: "t3" as Tool["id"], name: "execute", category: "execute" },
        { ...sampleTool, id: "t4" as Tool["id"], name: "write", category: "write" },
      ]
      const sorted = sortToolsByPriority(tools)
      expect(sorted[0]?.category).toBe("read")
      expect(sorted[1]?.category).toBe("write")
      expect(sorted[2]?.category).toBe("execute")
      expect(sorted[3]?.category).toBe("delegate")
    })
  })

  // ─── R2.2 ─────────────────────────────────────────────
  describe("validateToolDefinition (R2.2)", () => {
    it("accepts a read_file definition", () => {
      const def: ToolDefinition = {
        name: "read_file" as ToolName,
        parameters: {
          type: "object",
          properties: { path: { type: "string" } },
          required: ["path"],
        },
        result: { type: "string" },
        risk: "low",
      }
      const v = validateToolDefinition(def)
      expect(v.ok).toBe(true)
    })

    it("rejects a high-risk definition", () => {
      const def: ToolDefinition = {
        name: "delete_everything" as ToolName,
        parameters: {},
        result: {},
        risk: "high",
      }
      const v = validateToolDefinition(def)
      expect(v.ok).toBe(false)
      expect(v.reason).toContain("high")
    })

    it("rejects empty tool name", () => {
      const def: ToolDefinition = {
        name: "" as ToolName,
        parameters: {},
        result: {},
        risk: "low",
      }
      const v = validateToolDefinition(def)
      expect(v.ok).toBe(false)
    })
  })

  describe("describeCommandSpec (R2.2)", () => {
    it("describes a command spec without shell metacharacters", () => {
      const spec: CommandSpec = {
        executable: "ls",
        args: ["-la"],
        cwd: "/ws",
        timeoutMs: 1000,
        network: "none",
      }
      const desc = describeCommandSpec(spec)
      expect(desc.ok).toBe(true)
      expect(desc.executable).toBe("ls")
      expect(desc.args.join(" ")).toBe("-la")
      expect(desc.network).toBe("none")
    })

    it("rejects executable with shell metacharacter (no throw)", () => {
      const spec: CommandSpec = {
        executable: "ls;rm",
        args: [],
        cwd: "/ws",
        timeoutMs: 1000,
        network: "none",
      }
      const desc = describeCommandSpec(spec)
      expect(desc.ok).toBe(false)
      expect(desc.reason).toContain("shell metacharacter")
    })

    it("rejects arg with shell metacharacter (no throw)", () => {
      const spec: CommandSpec = {
        executable: "echo",
        args: ["hi;rm"],
        cwd: "/ws",
        timeoutMs: 1000,
        network: "none",
      }
      const desc = describeCommandSpec(spec)
      expect(desc.ok).toBe(false)
      expect(desc.reason).toContain("hi;rm")
    })
  })
})
