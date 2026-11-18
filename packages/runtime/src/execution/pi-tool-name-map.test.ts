import { describe, expect, it } from "vitest"
import { normalizePiToolName, PI_TO_BUTLER_TOOL_NAMES } from "./pi-tool-name-map.js"

describe("pi tool name map", () => {
  it("maps native tools to capability names", () => {
    expect(normalizePiToolName("read")).toBe("read_file")
    expect(normalizePiToolName("write")).toBe("write_file")
    expect(normalizePiToolName("edit")).toBe("write_file")
    expect(normalizePiToolName("bash")).toBe("run_command")
    expect(normalizePiToolName("grep")).toBe("run_command")
    expect(normalizePiToolName("find")).toBe("run_command")
    expect(normalizePiToolName("ls")).toBe("run_command")
  })

  it("keeps unknown names unchanged", () => {
    expect(normalizePiToolName("read_file")).toBe("read_file")
    expect(normalizePiToolName("custom")).toBe("custom")
    expect(Object.keys(PI_TO_BUTLER_TOOL_NAMES)).toHaveLength(7)
  })
})
