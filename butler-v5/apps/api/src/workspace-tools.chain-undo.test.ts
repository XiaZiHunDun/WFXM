import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import {
  makeRunCommandTool,
  makeWriteFileTool,
  resetUndoChain,
  resetUndoStack,
  undoChain,
} from "./workspace-tools.js"

let TMP: string
let FILE_A: string
let FILE_B: string

beforeEach(() => {
  TMP = mkdtempSync(join(tmpdir(), "chain-undo-"))
  FILE_A = join(TMP, "a.ts")
  FILE_B = join(TMP, "b.ts")
  writeFileSync(FILE_A, "OLD_A", "utf8")
  writeFileSync(FILE_B, "OLD_B", "utf8")
  resetUndoStack()
  resetUndoChain()
})

afterEach(() => {
  rmSync(TMP, { recursive: true, force: true })
})

describe("D49 chain undo — write_file push", () => {
  it("C1: writes push entries to UNDO_CHAIN when chainId present", async () => {
    const ctx = { chainId: "run-1", conversationId: "conv-1", workspaceRoot: TMP }
    const writeA = makeWriteFileTool(ctx)
    const writeB = makeWriteFileTool(ctx)
    const r1 = await writeA.run({ path: "a.ts", content: "NEW_A" })
    const r2 = await writeB.run({ path: "b.ts", content: "NEW_B" })
    expect(r1.ok).toBe(true)
    expect(r2.ok).toBe(true)

    const result = undoChain("run-1")
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(2)
    const first = result.reverted[0]
    expect(first?.entry.kind).toBe("write")
    if (first?.entry.kind === "write") {
      expect(first.entry.path).toBe(FILE_B)
    }
    expect(result.reverted.every(r => r.ok)).toBe(true)

    // Read-back: verify file content actually restored
    expect(readFileSync(FILE_A, "utf8")).toBe("OLD_A")
    expect(readFileSync(FILE_B, "utf8")).toBe("OLD_B")
  })
})

describe("D49 chain undo — run_command push", () => {
  it("C2: mixed write + command push captures argv/cwd/gitStatusBeforeHash", async () => {
    const ctx = { chainId: "run-2", workspaceRoot: TMP }
    const write = makeWriteFileTool(ctx)
    const runCmd = makeRunCommandTool(ctx)
    await write.run({ path: "a.ts", content: "X" })
    await runCmd.run({ argv: ["echo", "hello"] })
    await write.run({ path: "b.ts", content: "Y" })

    const result = undoChain("run-2")
    expect(result).toBeDefined()
    if (!result) return
    // 2 writes reverted, 1 command in side-effects (no auto-revert)
    expect(result.reverted).toHaveLength(2)
    expect(result.commandSideEffects).toHaveLength(1)
    expect(result.commandSideEffects[0]?.argv).toEqual(["echo", "hello"])
    // reverse order: b.ts first, then a.ts
    const firstWrite = result.reverted[0]?.entry
    expect(firstWrite?.kind).toBe("write")
    if (firstWrite?.kind === "write") {
      expect(firstWrite.path).toBe(FILE_B)
    }
  })
})