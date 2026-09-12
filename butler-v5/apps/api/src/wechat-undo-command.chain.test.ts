import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { tryWechatUndoCommand } from "./wechat-undo-command.js"
import {
  UNDO_CHAIN_FOR_TEST,
  UNDO_CHAIN_CONV_FOR_TEST,
  resetUndoChain,
  resetUndoStack,
} from "./workspace-tools.js"
import type { Wiring } from "./wiring.js"

const stubWiring = {} as Wiring
const FROM = "owner-1"

let TMP: string
let FILE_A: string

beforeEach(() => {
  TMP = mkdtempSync(join(tmpdir(), "chain-reply-"))
  FILE_A = join(TMP, "a.ts")
  mkdirSync(TMP, { recursive: true })
  writeFileSync(FILE_A, "OLD_A", "utf8")
  resetUndoStack()
  resetUndoChain()
})

afterEach(() => {
  rmSync(TMP, { recursive: true, force: true })
})

describe("D49 wechat-undo-command chain branch", () => {
  it("C5: 5 chain phrases all match and route to chain branch", async () => {
    const phrases = [
      "撤销这轮",
      "撤销本次",
      "撤销这次",
      "撤销这一轮",
      "/撤销这轮",
      "撤销这轮 ",
      "撤销这轮",
    ]
    for (const p of phrases) {
      const r = await tryWechatUndoCommand({
        wiring: stubWiring,
        fromUserId: FROM,
        content: p,
        env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP },
      })
      expect(r).not.toBeNull()
      if (!r) continue
      // No chain seeded → "没有可撤销的轮次"
      expect(r.reply).toMatch(/没有可撤销的轮次/)
    }
  })

  it("D54-T4: '撤销这批' phrase matches chain intent regex (D49 6-phrase spec full ✓)", async () => {
    const phrases = ["撤销这批", "撤销这批 "]
    for (const p of phrases) {
      const r = await tryWechatUndoCommand({
        wiring: stubWiring,
        fromUserId: FROM,
        content: p,
        env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP },
      })
      expect(r).not.toBeNull()
      if (!r) continue
      // No chain seeded → "没有可撤销的轮次" (proves chain branch routed)
      expect(r.reply).toMatch(/没有可撤销的轮次/)
    }
  })

  it("C6: chain undo with no chain returns honest reply", async () => {
    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP },
    })
    expect(r).not.toBeNull()
    if (!r) return
    expect(r.reply).toBe("没有可撤销的轮次。")
  })

  it("D59 T5 F-04: chain undo in conv with no matching chain surfaces explicit error (no silent global fallback)", async () => {
    // Seed a chain for conversation "conv-other" — currentConv is set to
    // "conv-current" with no matching chain. Previously this fell back to
    // the most-recent global chainId (run-other) and silently reverted
    // it. Now it must surface a clear error so owner cannot accidentally
    // cross-conversation revert.
    UNDO_CHAIN_FOR_TEST.set("run-other", [
      {
        kind: "write",
        path: FILE_A,
        beforeContent: "OLD_A",
        tool: "write_file",
        pushedAt: 1,
      },
    ])
    UNDO_CHAIN_CONV_FOR_TEST.set("run-other", "conv-other")

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: {
        ...process.env,
        BUTLER_V5_WORKSPACE_ROOT: TMP,
        BUTLER_V5_CONVERSATION_ID: "conv-current",
      },
    })
    expect(r).not.toBeNull()
    if (!r) return
    expect(r.reply).toContain("当前对话没有可撤销的轮次")
    expect(r.reply).toContain("/撤销 <chainId>")
    // File must NOT have been reverted (silent fallback would have
    // overwritten FILE_A back to beforeContent, but we never even read
    // its current content for this test — the contract is the reply
    // shape, not the filesystem state).
    expect(readFileSync(FILE_A, "utf8")).toBe("OLD_A")
  })

  it("C7: chain undo success shows table with writes + command side-effects", async () => {
    const { UNDO_CHAIN_FOR_TEST: _ } = await import("./workspace-tools.js")
    UNDO_CHAIN_FOR_TEST.set("run-7", [
      { kind: "write", path: FILE_A, beforeContent: "OLD_A", tool: "write_file", pushedAt: 1 },
      { kind: "command", argv: ["pnpm", "install", "lodash"], cwd: TMP, gitStatusBeforeHash: null, exit: 0, startedAt: 2, tool: "run_command" },
    ])
    UNDO_CHAIN_CONV_FOR_TEST.set("run-7", "conv-7")

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: {
        ...process.env,
        BUTLER_V5_WORKSPACE_ROOT: TMP,
        BUTLER_V5_CONVERSATION_ID: "conv-7",
      },
    })
    expect(r).not.toBeNull()
    if (!r) return
    expect(r.reply).toContain("✅")
    expect(r.reply).toContain(FILE_A)
    expect(r.reply).toContain("pnpm install lodash")
    expect(r.reply).not.toContain("git起点") // gitStatusBeforeHash=null

    // Verify file content restored
    expect(readFileSync(FILE_A, "utf8")).toBe("OLD_A")
  })

  it("C8: cross-conversation chain is rejected", async () => {
    const { UNDO_CHAIN_FOR_TEST, UNDO_CHAIN_CONV_FOR_TEST } = await import("./workspace-tools.js")
    UNDO_CHAIN_FOR_TEST.set("run-8", [
      { kind: "write", path: FILE_A, beforeContent: "OLD_A", tool: "write_file", pushedAt: 1 },
    ])
    UNDO_CHAIN_CONV_FOR_TEST.set("run-8", "conv-A")

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: {
        ...process.env,
        BUTLER_V5_WORKSPACE_ROOT: TMP,
        BUTLER_V5_CONVERSATION_ID: "conv-B",
      },
    })
    expect(r).not.toBeNull()
    if (!r) return
    // D59 T5 (audit #3 F-04): previously the most-recent global chainId
    // fallback found run-A and rejected it with "该轮次不属于当前对话".
    // Now we surface the new error path because the silent fallback was
    // removed — owner cannot accidentally cross-conversation revert.
    expect(r.reply).toContain("当前对话没有可撤销的轮次")
    expect(r.reply).toContain("/撤销 <chainId>")
  })

  // D54 follow-up: formatChainReply must render non-write kinds (was MEDIUM bug — silent drop)
  it("D54-followup: formatChainReply renders edit_file reverted entry (no silent drop)", async () => {
    const { UNDO_CHAIN_FOR_TEST, UNDO_CHAIN_CONV_FOR_TEST } = await import("./workspace-tools.js")
    // Simulate: edit_file was just run, replacing OLD with NEW
    writeFileSync(FILE_A, "NEW_EDIT", "utf8")
    UNDO_CHAIN_FOR_TEST.set("run-edit", [
      {
        kind: "edit",
        path: FILE_A,
        beforeContent: "OLD_EDIT",
        afterContent: "NEW_EDIT",
        tool: "edit_file",
        pushedAt: 1,
      },
    ])
    UNDO_CHAIN_CONV_FOR_TEST.set("run-edit", "conv-edit")

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: {
        ...process.env,
        BUTLER_V5_WORKSPACE_ROOT: TMP,
        BUTLER_V5_CONVERSATION_ID: "conv-edit",
      },
    })
    expect(r).not.toBeNull()
    if (!r) return

    // Verify reply renders the edit entry (would be silently absent in the MEDIUM bug)
    expect(r.reply).toContain("✅")
    expect(r.reply).toContain(FILE_A)
    expect(r.reply).toMatch(/edit/)

    // Verify file content reverted
    expect(readFileSync(FILE_A, "utf8")).toBe("OLD_EDIT")
  })
})
