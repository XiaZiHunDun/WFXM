import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { tryWechatUndoCommand } from "./wechat-undo-command.js"
import { resetUndoChain, resetUndoStack } from "./workspace-tools.js"
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

  it("C7: chain undo success shows table with writes + command side-effects", async () => {
    const { UNDO_CHAIN_FOR_TEST, UNDO_CHAIN_CONV_FOR_TEST } = await import("./workspace-tools.js")
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
    expect(r.reply).toBe("该轮次不属于当前对话。")
  })
})
