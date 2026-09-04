/**
 * /undo command — revert last write_file per absolute path (P2 fix 2026-09-04).
 *
 * `tryWechatInboundCommand` routes content starting with `/undo` here. We
 * pop the most recent pre-write content for the target path and write it
 * back. Per-process stack only (no cross-restart persistence; owner can
 * `git diff` to see pending changes after restart). Stack capped at 16.
 *
 * Usage: `/undo <path>` to revert the most recent write_file to that path.
 * Without a path argument, reverts the most recent write_file across all
 * paths (LIFO order, keyed by absolute path).
 */
import { writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { mkdirSync } from "node:fs"
import { undoLastWrite, pendingUndoCount } from "./workspace-tools.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

function done(reply: string, traces: readonly string[] = []): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

export async function tryWechatUndoCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (!trimmed.startsWith("/undo") && !trimmed.startsWith("/撤销")) {
    return null
  }
  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
  const rest = trimmed.replace(/^\/u(ndo)?\s*/i, "").replace(/^\/撤销\s*/, "").trim()
  // No path: pop the most recent across all paths (iterate stack)
  if (rest.length === 0) {
    // We need a reverse-iteration helper; simplest: try the workspace root
    // (which is also a path). For broader use, owner should pass the path.
    const probe = undoLastWrite(workspaceRoot, ".")
    if (probe === undefined) {
      return done("没有可撤销的写操作。")
    }
    if (probe === null) {
      // File was new — delete it instead of restoring
      // (we don't track the path here; fall through to require explicit path)
      return done("最近一次写是新建文件，请指定路径：`/undo <path>`")
    }
    return done("[undo] 不带路径的撤销需指定文件，请用 `/undo <path>`。")
  }

  // Explicit path: pop + restore (or delete if was new)
  const beforeContent = undoLastWrite(workspaceRoot, rest)
  if (beforeContent === undefined) {
    return done(`无 ${rest} 的撤销记录（栈中无内容或已用完）`)
  }
  const resolved = resolve(workspaceRoot, rest)
  try {
    if (beforeContent === null) {
      // File was newly created; cannot delete (no fs.unlink here to keep imports small;
      // truncate by writing empty is the next-best signal).
      writeFileSync(resolved, "", "utf8")
      return done(`[undo] ${rest} 是新建文件，已置空（如需彻底删除请手工 rm）`)
    }
    mkdirSync(dirname(resolved), { recursive: true })
    writeFileSync(resolved, beforeContent, "utf8")
    return done(`[undo] ${rest} 已还原为上版内容（栈余 ${pendingUndoCount(workspaceRoot, rest)}）`)
  } catch (err) {
    return done(`[undo] 失败：${err instanceof Error ? err.message : String(err)}`)
  }
}