/**
 * /undo command — revert last write_file per absolute path (P2 batch 2026-09-08).
 *
 * Routes content matching `/undo` / `/撤销` / 中文自然语言
 * (撤销 / 撤销刚才 / 撤销上一步 / 撤销上次 / 撤销上一次 / undo) here.
 *
 * Behavior:
 * - `/undo <path>` / `/撤销 <path>` — pop + restore specific path.
 * - 中文 NL (撤销刚才 / etc.) without path — pop the most recent write_file
 *   across all paths. If the undo stack is empty, return honest "没有可撤销
 *   的写操作" reply.
 * - 显式 `/undo` / `/撤销` without path — graceful "请用 `/undo <path>`" reply.
 *
 * Per-process undo stack only (no cross-restart persistence; owner can
 * `git diff` to see pending changes after restart). Stack capped at 16.
 */
import { writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { mkdirSync } from "node:fs"
import {
  undoLastWrite,
  popMostRecentWrite,
  undoChain,
  getUndoChainConversation,
  undoChain_listConversations,
} from "./workspace-tools.js"
import type { ChainRevertResult } from "./workspace-tools.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

// Match an undo intent at the start of trimmed content, optionally followed
// by whitespace. Allow trailing content (path) so `/undo foo.txt` keeps
// working; rest is then the path. Order alternatives longest-first so
// `撤销刚才` wins over `撤销` (regex alternation is first-match, not longest).
const UNDO_INTENT_REGEX =
  /^(撤销这一轮|撤销这轮|撤销本次|撤销这次|撤销刚才|撤销上一步|撤销上一次|撤销上次|撤销|\/undo|\/撤销|\/撤销这轮|undo)\s*/i

// D49: chain intent (multi-tool turn undo). Match longest-first.
// D54 T4: add "撤销这批" (6th phrase from D49 6-phrase spec → 6 of 6 impl, FULL ✓).
const CHAIN_INTENT_REGEX =
  /^(撤销这一轮|撤销这轮|撤销这批|撤销本次|撤销这次|\/撤销这轮)\s*$/i

// "Explicit" form: leading `/undo` or `/撤销` (slash prefix). The full match
// (no trailing path) triggers the graceful "请用 /undo <path>" fallback.
const EXPLICIT_UNDO_REGEX = /^(\/undo|\/撤销)\s*$/i

function done(reply: string, traces: readonly string[] = []): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

function restoreAndReply(
  absolutePath: string,
  displayPath: string,
  content: string | null,
): ButlerLoopResult {
  try {
    if (content === null) {
      writeFileSync(absolutePath, "", "utf8")
      return done(`[undo] ${displayPath} 是新建文件，已置空（如需彻底删除请手工 rm）`)
    }
    mkdirSync(dirname(absolutePath), { recursive: true })
    writeFileSync(absolutePath, content, "utf8")
    return done(`[undo] ${displayPath} 已还原为上版内容`)
  } catch (err) {
    return done(`[undo] 失败：${err instanceof Error ? err.message : String(err)}`)
  }
}

function formatChainReply(result: ChainRevertResult): string {
  const lines: string[] = []
  lines.push(`[撤销轮次 chainId=${result.chainId}]`)
  for (const r of result.reverted) {
    const ok = r.ok ? "✅" : "❌"
    const reason = r.ok ? "" : ` (${r.reason ?? "失败"})`
    switch (r.entry.kind) {
      case "write": {
        const label = r.entry.beforeContent === null ? "新建文件已置空" : "还原为上版"
        lines.push(`${ok} ${r.entry.path} → ${label}${reason}`)
        break
      }
      case "edit": {
        const label = r.entry.beforeContent === null ? "edit 已置空" : "edit 已还原"
        lines.push(`${ok} ${r.entry.path} → ${label}${reason}`)
        break
      }
      case "patch": {
        const label = r.entry.beforeContent === null ? "patch 无 before" : "patch 已还原"
        lines.push(`${ok} ${r.entry.path} → ${label}${reason}`)
        break
      }
      case "delete": {
        const label = r.entry.beforeContent === null ? "删除无 before" : "文件已重建"
        lines.push(`${ok} ${r.entry.path} → ${label}${reason}`)
        break
      }
      case "command": {
        // Command entries don't appear in reverted (they appear in commandSideEffects).
        // Unreachable in practice, but TypeScript requires exhaustiveness.
        lines.push(`${ok} <command>${reason}`)
        break
      }
    }
  }
  if (result.commandSideEffects.length > 0) {
    lines.push("")
    lines.push(`以下 ${result.commandSideEffects.length} 个命令副作用需手工 reverse（无法自动 undo）：`)
    for (const s of result.commandSideEffects) {
      lines.push(`• ${s.argv.join(" ")}`)
    }
  }
  if (result.gitHeadBefore) {
    lines.push("")
    lines.push(`git起点: ${result.gitHeadBefore}（undo 前 HEAD）`)
  }
  return lines.join("\n")
}

export async function tryWechatUndoCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (!UNDO_INTENT_REGEX.test(trimmed)) {
    return null
  }

  const workspaceRoot =
    (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
  const rest = trimmed.replace(UNDO_INTENT_REGEX, "").trim()
  const isExplicit = EXPLICIT_UNDO_REGEX.test(trimmed)

  // D49: chain 分支 — 在 explicit 判断前先判 chain intent
  if (CHAIN_INTENT_REGEX.test(trimmed)) {
    const currentConv = env["BUTLER_V5_CONVERSATION_ID"]?.trim()
    let chainId: string | undefined
    if (currentConv) {
      for (const [cid, conv] of undoChain_listConversations()) {
        if (conv === currentConv) {
          chainId = cid
          break
        }
      }
    }
    // D59 T5 (audit #3 F-04): previously when no chainId matched the
    // current conversation we silently fell back to the most-recent
    // global chainId via undoChain_listChainIds(). That fallback reverted
    // operations from a different (possibly other-owner) conversation
    // without confirmation. Surface a clear error instead — owner can
    // retry with /undo <chainId> explicitly if they meant a different
    // chain.
    if (!chainId) {
      if (currentConv) {
        return done(
          "当前对话没有可撤销的轮次。如果你想撤销其他对话的轮次，请用 `/撤销 <chainId>` 显式指定。",
          ["wechat-undo: chain not found for current conversation"],
        )
      }
      return done("没有可撤销的轮次。")
    }
    if (currentConv) {
      const stored = getUndoChainConversation(chainId)
      if (stored && stored !== currentConv) {
        return done("该轮次不属于当前对话。")
      }
    }
    const result = undoChain(chainId)
    if (!result) return done("当前轮次没有可撤销的操作。")
    return done(formatChainReply(result))
  }

  // 无 path 路径：分 explicit vs NL 两种行为
  if (rest.length === 0) {
    if (isExplicit) {
      // F2: 显式 /undo 无 path → graceful fallback
      return done("请用 `/undo <path>` 指定要还原的文件路径。")
    }
    // F1: 中文 NL 无 path → 找最近的写；没有就 honest "无可撤销"
    const most = popMostRecentWrite()
    if (most === undefined) {
      return done("没有可撤销的写操作。")
    }
    return restoreAndReply(most.path, most.path, most.content)
  }

  // 显式 path：pop + restore
  const beforeContent = undoLastWrite(workspaceRoot, rest)
  if (beforeContent === undefined) {
    return done(`无 ${rest} 的撤销记录（栈中无内容或已用完）`)
  }
  const resolved = resolve(workspaceRoot, rest)
  return restoreAndReply(resolved, rest, beforeContent)
}
