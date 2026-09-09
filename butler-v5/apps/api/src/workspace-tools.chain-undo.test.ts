import { describe, expect, it, beforeEach } from "vitest"
import { writeFileSync, mkdirSync, rmSync } from "node:fs"
import { join } from "node:path"
import {
  makeWriteFileTool,
  resetUndoStack,
  resetUndoChain,
} from "./workspace-tools.js"

const TMP = join(process.cwd(), ".tmp-chain-undo-test")
const FILE_A = join(TMP, "a.ts")
const FILE_B = join(TMP, "b.ts")

function setup() {
  rmSync(TMP, { recursive: true, force: true })
  mkdirSync(TMP, { recursive: true })
  writeFileSync(FILE_A, "OLD_A", "utf8")
  writeFileSync(FILE_B, "OLD_B", "utf8")
  resetUndoStack()
  resetUndoChain()
}

describe("D49 chain undo — write_file push", () => {
  beforeEach(setup)

  it("C1: writes push entries to UNDO_CHAIN when chainId present", async () => {
    const ctx = { chainId: "run-1", conversationId: "conv-1", workspaceRoot: TMP }
    const writeA = makeWriteFileTool(ctx)
    const writeB = makeWriteFileTool(ctx)
    const r1 = await writeA.run({ path: "a.ts", content: "NEW_A" })
    const r2 = await writeB.run({ path: "b.ts", content: "NEW_B" })
    expect(r1.ok).toBe(true)
    expect(r2.ok).toBe(true)

    const { undoChain } = await import("./workspace-tools.js")
    const result = undoChain("run-1")
    expect(result).toBeDefined()
    expect(result!.reverted).toHaveLength(2)
    expect(result!.reverted[0]!.entry.kind).toBe("write")
    expect((result!.reverted[0]!.entry as { path: string }).path).toBe(FILE_B)
    expect(result!.reverted[1]!.ok).toBe(true)
  })
})
