import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import {
  makeRunCommandTool,
  makeWriteFileTool,
  resetUndoChain,
  resetUndoStack,
  undoChain,
  UNDO_CHAIN_FOR_TEST,
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

describe("D49 chain undo — partial revert", () => {
  it("C3: reverse order revert; failures caught and continued; chain consumed", async () => {
    const ctx = { chainId: "run-3", workspaceRoot: TMP }
    const write = makeWriteFileTool(ctx)
    await write.run({ path: "a.ts", content: "NEW_A" })
    await write.run({ path: "b.ts", content: "NEW_B" })
    await write.run({ path: "c.ts", content: "NEW_C" })

    // Force a failure on b.ts revert by chmod readonly (best-effort; may
    // not work on Windows/root; the catch-block path is still exercised
    // by the spec-described ENOENT scenario in production).
    try {
      chmodSync(FILE_B, 0o444)
    } catch {
      // skip if chmod unsupported
    }

    const result = undoChain("run-3")
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(3)
    // Reverse order: c.ts first, then b.ts, then a.ts
    const firstWrite = result.reverted[0]?.entry
    const secondWrite = result.reverted[1]?.entry
    const thirdWrite = result.reverted[2]?.entry
    expect(firstWrite?.kind).toBe("write")
    if (firstWrite?.kind === "write") {
      expect(firstWrite.path).toBe(join(TMP, "c.ts"))
    }
    expect(secondWrite?.kind).toBe("write")
    if (secondWrite?.kind === "write") {
      expect(secondWrite.path).toBe(FILE_B)
    }
    expect(thirdWrite?.kind).toBe("write")
    if (thirdWrite?.kind === "write") {
      expect(thirdWrite.path).toBe(FILE_A)
    }

    // Restore perms for cleanup (if chmod was applied)
    try {
      chmodSync(FILE_B, 0o644)
    } catch {
      // ignore
    }

    // Chain consumed — second call returns undefined
    const result2 = undoChain("run-3")
    expect(result2).toBeUndefined()
  })
})

describe("D49 chain undo — resetUndoChain", () => {
  beforeEach(() => {
    TMP = mkdtempSync(join(tmpdir(), "chain-undo-"))
    FILE_A = join(TMP, "a.ts")
    writeFileSync(FILE_A, "OLD_A", "utf8")
    resetUndoStack()
    resetUndoChain()
  })

  afterEach(() => {
    rmSync(TMP, { recursive: true, force: true })
  })

  it("C4: resetUndoChain clears UNDO_CHAIN + UNDO_CHAIN_CONV + git cache", async () => {
    const ctx = { chainId: "run-x", workspaceRoot: TMP }
    const write = makeWriteFileTool(ctx)
    await write.run({ path: "a.ts", content: "Z" })
    expect(undoChain("run-x")).toBeDefined()

    resetUndoChain()
    expect(undoChain("run-x")).toBeUndefined()
  })
})

describe("D54 chain undo — edit_file push", () => {
  it("E1: undoChain reverts edit_file entry by restoring beforeContent", async () => {
    const chainId = "run-edit-1"
    const path = join(TMP, "edit.txt")
    const beforeContent = "line 1\nline 2\n"
    const afterContent = "line 1\nline 2 modified\n"

    // Simulate edit_file: file starts at beforeContent, edit moves it to afterContent.
    writeFileSync(path, afterContent, "utf8")

    // Manually push an edit_file ChainEntry (no makeEditFileTool yet).
    const chain = UNDO_CHAIN_FOR_TEST.get(chainId) ?? []
    chain.push({
      kind: "edit",
      path,
      beforeContent,
      afterContent,
      tool: "edit_file",
      pushedAt: Date.now(),
    })
    UNDO_CHAIN_FOR_TEST.set(chainId, chain)

    // Verify entry stored
    const stored = UNDO_CHAIN_FOR_TEST.get(chainId)
    expect(stored).toHaveLength(1)
    expect(stored?.[0]?.kind).toBe("edit")
    if (stored?.[0]?.kind === "edit") {
      expect(stored[0].path).toBe(path)
      expect(stored[0].beforeContent).toBe(beforeContent)
      expect(stored[0].afterContent).toBe(afterContent)
      expect(stored[0].tool).toBe("edit_file")
    }

    // Revert
    const result = undoChain(chainId)
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(1)
    expect(result.reverted[0]?.ok).toBe(true)
    expect(result.reverted[0]?.entry.kind).toBe("edit")

    // Verify file content restored
    expect(readFileSync(path, "utf8")).toBe(beforeContent)
  })
})

describe("D54 chain undo — apply_patch push", () => {
  it("E2: undoChain reverts apply_patch entry by restoring beforeContent", async () => {
    const chainId = "run-patch-1"
    const path = join(TMP, "patch.txt")
    const beforeContent = "line 1\nline 2\n"
    const afterContent = "line 1\nline 2 modified\n"
    // Unified-diff representation of the patch that produced afterContent.
    const patchContent = "@@ -1,2 +1,2 @@\n line 1\n-line 2\n+line 2 modified\n"

    // Simulate apply_patch: file starts at beforeContent, patch moves it to afterContent.
    writeFileSync(path, afterContent, "utf8")

    // Manually push an apply_patch ChainEntry (no makeApplyPatchTool yet).
    const chain = UNDO_CHAIN_FOR_TEST.get(chainId) ?? []
    chain.push({
      kind: "patch",
      path,
      beforeContent,
      patchContent,
      tool: "apply_patch",
      pushedAt: Date.now(),
    })
    UNDO_CHAIN_FOR_TEST.set(chainId, chain)

    // Verify entry stored
    const stored = UNDO_CHAIN_FOR_TEST.get(chainId)
    expect(stored).toHaveLength(1)
    expect(stored?.[0]?.kind).toBe("patch")
    if (stored?.[0]?.kind === "patch") {
      expect(stored[0].path).toBe(path)
      expect(stored[0].beforeContent).toBe(beforeContent)
      expect(stored[0].patchContent).toBe(patchContent)
      expect(stored[0].tool).toBe("apply_patch")
    }

    // Revert (best-effort: write beforeContent back, don't try git apply -R).
    const result = undoChain(chainId)
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(1)
    expect(result.reverted[0]?.ok).toBe(true)
    expect(result.reverted[0]?.entry.kind).toBe("patch")

    // Verify file content restored
    expect(readFileSync(path, "utf8")).toBe(beforeContent)
  })

  it("E2b: undoChain marks apply_patch revert as failed when beforeContent is null", async () => {
    const chainId = "run-patch-2"
    const path = join(TMP, "patch-noop.txt")

    // No beforeContent captured — best-effort revert cannot restore.
    const chain = UNDO_CHAIN_FOR_TEST.get(chainId) ?? []
    chain.push({
      kind: "patch",
      path,
      beforeContent: null,
      patchContent: "@@ -1 +1 @@\n-old\n+new\n",
      tool: "apply_patch",
      pushedAt: Date.now(),
    })
    UNDO_CHAIN_FOR_TEST.set(chainId, chain)

    const result = undoChain(chainId)
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(1)
    expect(result.reverted[0]?.ok).toBe(false)
    expect(result.reverted[0]?.reason).toBe("no before state captured")
  })
})

describe("D54 chain undo — delete_file push", () => {
  it("E3: undoChain reverts delete_file entry by recreating file with beforeContent", async () => {
    const chainId = "run-delete-1"
    const path = join(TMP, "delete.txt")
    const beforeContent = "line 1\nline 2\n"

    // Simulate delete_file: file existed at beforeContent, then got deleted.
    // Set up the deleted state: file removed from disk, beforeContent captured.
    writeFileSync(path, beforeContent, "utf8")
    const chain = UNDO_CHAIN_FOR_TEST.get(chainId) ?? []
    chain.push({
      kind: "delete",
      path,
      beforeContent,
      tool: "delete_file",
      pushedAt: Date.now(),
    })
    UNDO_CHAIN_FOR_TEST.set(chainId, chain)

    // Simulate the tool actually deleting the file from disk.
    unlinkSync(path)
    expect(existsSync(path)).toBe(false)

    // Verify entry stored
    const stored = UNDO_CHAIN_FOR_TEST.get(chainId)
    expect(stored).toHaveLength(1)
    expect(stored?.[0]?.kind).toBe("delete")
    if (stored?.[0]?.kind === "delete") {
      expect(stored[0].path).toBe(path)
      expect(stored[0].beforeContent).toBe(beforeContent)
      expect(stored[0].tool).toBe("delete_file")
    }

    // Revert: should recreate the file with beforeContent.
    const result = undoChain(chainId)
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(1)
    expect(result.reverted[0]?.ok).toBe(true)
    expect(result.reverted[0]?.entry.kind).toBe("delete")

    // Verify file recreated with original content
    expect(existsSync(path)).toBe(true)
    expect(readFileSync(path, "utf8")).toBe(beforeContent)
  })

  it("E3b: undoChain marks delete_file revert as failed when beforeContent is null", async () => {
    const chainId = "run-delete-2"
    const path = join(TMP, "delete-noop.txt")

    // No beforeContent captured — cannot safely recreate the file.
    const chain = UNDO_CHAIN_FOR_TEST.get(chainId) ?? []
    chain.push({
      kind: "delete",
      path,
      beforeContent: null,
      tool: "delete_file",
      pushedAt: Date.now(),
    })
    UNDO_CHAIN_FOR_TEST.set(chainId, chain)

    const result = undoChain(chainId)
    expect(result).toBeDefined()
    if (!result) return
    expect(result.reverted).toHaveLength(1)
    expect(result.reverted[0]?.ok).toBe(false)
    expect(result.reverted[0]?.reason).toBe("no before state captured")
  })
})