/**
 * D75 T1 (CQ-003): undo module extracted from workspace-tools.ts.
 *
 * Owns the in-memory undo state + helpers for both single-file undo
 * (`undoLastWrite` / `popMostRecentWrite`) and chain-aware multi-tool
 * undo (`undoChain` + D49 chain push). State is module-level so it
 * survives across tool calls in the same process; per-process only
 * (no cross-restart persistence).
 *
 * Extracted to bring workspace-tools.ts under the 800-line hard cap
 * (was 811 → now ~570 after this split).
 */
import { execFile } from "node:child_process"
import { mkdirSync, unlinkSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import type { WorkspaceToolContext } from "./workspace-tools.js"

// In-memory write undo stack (P2 fix 2026-09-04). Module-level so it
// survives across tool calls in the same process; per-process only (no
// cross-restart persistence, owner can `git diff` to see pending changes
// after restart). Keyed by absolute path; each write_file pushes the
// pre-write content (or `null` for new files). undoLastWrite pops and
// restores. Capped at 16 entries per path to bound memory.
const UNDO_STACK = new Map<string, (string | null)[]>()
const UNDO_CAP = 16

// P2 batch v2 (2026-09-08): monotonic touch counter so we can find the
// most-recent write across all paths. Touched on every push; popMostRecent
// scans the map for the highest counter and pops that path's stack.
let UNDO_TOUCH_COUNTER = 0
const UNDO_TOUCHED = new Map<string, number>()

// D49: chain-aware undo (multi-tool turn). chainId = runId.
const CHAIN_CAP = 32

export type ChainEntry =
  | {
      readonly kind: "write"
      readonly path: string
      readonly beforeContent: string | null
      readonly tool: "write_file"
      readonly pushedAt: number
    }
  | {
      readonly kind: "edit"
      readonly path: string
      readonly beforeContent: string | null
      readonly afterContent: string | null
      readonly tool: "edit_file"
      readonly pushedAt: number
    }
  | {
      readonly kind: "command"
      readonly argv: readonly string[]
      readonly cwd: string
      readonly gitStatusBeforeHash: string | null
      readonly exit: number | null
      readonly startedAt: number
      readonly tool: "run_command"
    }
  | {
      readonly kind: "patch"  // D54 T2: apply_patch ChainEntry
      readonly path: string
      readonly beforeContent: string | null
      readonly patchContent: string  // unified diff format
      readonly tool: "apply_patch"
      readonly pushedAt: number
    }
  | {
      readonly kind: "delete"  // D54 T3: delete_file ChainEntry
      readonly path: string
      readonly beforeContent: string | null
      readonly tool: "delete_file"
      readonly pushedAt: number
    }

export interface ChainRevertResult {
  readonly chainId: string
  readonly reverted: readonly {
    readonly entry: ChainEntry
    readonly ok: boolean
    readonly reason?: string
  }[]
  readonly commandSideEffects: readonly {
    readonly argv: readonly string[]
    readonly note: string
  }[]
  readonly gitHeadBefore: string | null
}

const UNDO_CHAIN = new Map<string, ChainEntry[]>()
const UNDO_CHAIN_CONV = new Map<string, string>()

/** @internal — exported for tests only. Production code uses undoChain(). */
export const UNDO_CHAIN_FOR_TEST = UNDO_CHAIN
/** @internal — exported for tests only. */
export const UNDO_CHAIN_CONV_FOR_TEST = UNDO_CHAIN_CONV

/**
 * Module-level git HEAD cache for `undoChain` `gitHeadBefore`. Three-state:
 *   - `undefined` = not yet queried (first `_safeGitHead` call will populate)
 *   - `null` = queried but not a git repo / subprocess failed
 *   - `string` = commit hash
 * Populated by `_safeGitHead` (Task 2's run_command chain push); cleared by
 * `resetUndoChain` (test-only).
 */
let GIT_HEAD_CACHE: string | null | undefined

/**
 * Read current git HEAD for `cwd`, with module-level memoization.
 * Spec §2.2 + D49 plan Task 1 Step 3(b): `undoChain` records the pre-revert
 * head so we can detect no-op reverts (HEAD unchanged). Cached to avoid
 * spawning a git subprocess per call. Returns null on any error (not a git
 * repo, timeout, etc.) — best-effort.
 */
// Used by Task 2's run_command chain push to populate GIT_HEAD_CACHE.
async function _safeGitHead(cwd: string): Promise<string | null> {
  if (GIT_HEAD_CACHE !== undefined) return GIT_HEAD_CACHE
  try {
    const out = await new Promise<string>((resolveP, rejectP) => {
      execFile(
        "git",
        ["rev-parse", "HEAD"],
        { cwd, timeout: 2000 },
        (err, stdout) => (err ? rejectP(err) : resolveP(String(stdout).trim())),
      )
    })
    GIT_HEAD_CACHE = out || null
    return GIT_HEAD_CACHE
  } catch {
    GIT_HEAD_CACHE = null
    return null
  }
}

/** Test-only: clear UNDO_CHAIN + UNDO_CHAIN_CONV + git cache. */
export function resetUndoChain(): void {
  UNDO_CHAIN.clear()
  UNDO_CHAIN_CONV.clear()
  GIT_HEAD_CACHE = undefined
}

/** Get conversationId stored for a chainId, or undefined if no entry. */
export function getUndoChainConversation(chainId: string): string | undefined {
  return UNDO_CHAIN_CONV.get(chainId)
}

/** List all chainId↔conversationId pairs (insertion order). */
export function undoChain_listConversations(): readonly [string, string][] {
  return [...UNDO_CHAIN_CONV.entries()]
}

/** List all chainIds in insertion order. */
export function undoChain_listChainIds(): readonly string[] {
  return [...UNDO_CHAIN.keys()]
}

/** D49: push a run_command entry into UNDO_CHAIN if chainId present. */
async function pushCommandToChain(
  ctx: WorkspaceToolContext,
  argv: readonly string[],
  cwd: string,
  started: number,
  exitCode: number | null,
): Promise<void> {
  if (!ctx.chainId) return
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) {
    entries = []
    UNDO_CHAIN.set(ctx.chainId, entries)
  }
  const gitHead = await _safeGitHead(cwd)
  entries.push({
    kind: "command",
    argv,
    cwd,
    gitStatusBeforeHash: gitHead,
    exit: exitCode,
    startedAt: started,
    tool: "run_command",
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  if (ctx.conversationId) UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId)
}

/** Pop the most recent before-content for `path` (returns undefined if empty). */
export function undoLastWrite(workspaceRoot: string, path: string): string | null | undefined {
  const resolved = resolve(workspaceRoot, path)
  const stack = UNDO_STACK.get(resolved)
  if (!stack || stack.length === 0) return undefined
  const content = stack.pop() ?? null
  if (stack.length === 0) {
    UNDO_STACK.delete(resolved)
    UNDO_TOUCHED.delete(resolved)
  }
  return content
}

/**
 * Pop the most recent write across ALL paths. Returns `{ path, content }`
 * where content is `null` if the file was newly created, or `undefined` if
 * the undo stack is empty. Used by 中文 NL "撤销刚才" intent.
 */
export function popMostRecentWrite(): { path: string; content: string | null } | undefined {
  let bestPath: string | undefined
  let bestTouch = 0
  for (const [path, touch] of UNDO_TOUCHED.entries()) {
    if (touch > bestTouch) {
      bestTouch = touch
      bestPath = path
    }
  }
  if (bestPath === undefined) return undefined
  const stack = UNDO_STACK.get(bestPath)
  if (!stack || stack.length === 0) return undefined
  const content = stack.pop() ?? null
  if (stack.length === 0) {
    UNDO_STACK.delete(bestPath)
    UNDO_TOUCHED.delete(bestPath)
  }
  return { path: bestPath, content }
}

/** Reset undo stack (test-only). Clears all paths + touch counters. */
export function resetUndoStack(): void {
  UNDO_STACK.clear()
  UNDO_TOUCHED.clear()
  UNDO_TOUCH_COUNTER = 0
}

/**
 * D49: revert all writes tracked for `chainId`, in reverse order (newest
 * first). Best-effort: each entry succeeds or fails independently.
 * Consumes the chain on completion (success or failure).
 *
 * Task 1 minimal impl: only `kind: "write"` entries are reverted.
 * `kind: "command"` entries are skipped silently (full handling lands
 * in Task 2 once run_command pushes its entries).
 */
export function undoChain(chainId: string): ChainRevertResult | undefined {
  const entries = UNDO_CHAIN.get(chainId)
  if (!entries || entries.length === 0) return undefined
  const gitHeadBefore = GIT_HEAD_CACHE ?? null
  const reverted: { entry: ChainEntry; ok: boolean; reason?: string }[] = []
  const commandSideEffects: { argv: readonly string[]; note: string }[] = []
  for (const entry of [...entries].reverse()) {
    if (entry.kind === "write") {
      try {
        if (entry.beforeContent === null) {
          writeFileSync(entry.path, "", "utf8")
        } else {
          mkdirSync(dirname(entry.path), { recursive: true })
          writeFileSync(entry.path, entry.beforeContent, "utf8")
        }
        reverted.push({ entry, ok: true })
      } catch (err) {
        reverted.push({
          entry,
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        })
      }
    } else if (entry.kind === "edit") {
      // D54: edit_file revert — restore beforeContent.
      // null beforeContent = file was newly created by this edit; revert by deleting.
      try {
        if (entry.beforeContent === null) {
          try {
            unlinkSync(entry.path)
          } catch (unlinkErr) {
            // ENOENT is fine — already gone
            if ((unlinkErr as NodeJS.ErrnoException).code !== "ENOENT") throw unlinkErr
          }
        } else {
          mkdirSync(dirname(entry.path), { recursive: true })
          writeFileSync(entry.path, entry.beforeContent, "utf8")
        }
        reverted.push({ entry, ok: true })
      } catch (err) {
        reverted.push({
          entry,
          ok: false,
          reason: err instanceof Error ? err.message : String(err),
        })
      }
    } else if (entry.kind === "patch") {
      // D54 T2: apply_patch revert — best-effort, write beforeContent back.
      // Don't try to apply -R patch; just restore the prior snapshot.
      // null beforeContent = no snapshot captured; cannot revert.
      if (entry.beforeContent === null) {
        reverted.push({ entry, ok: false, reason: "no before state captured" })
      } else {
        try {
          mkdirSync(dirname(entry.path), { recursive: true })
          writeFileSync(entry.path, entry.beforeContent, "utf8")
          reverted.push({ entry, ok: true })
        } catch (err) {
          reverted.push({
            entry,
            ok: false,
            reason: err instanceof Error ? err.message : String(err),
          })
        }
      }
    } else if (entry.kind === "delete") {
      // D54 T3: delete_file revert — recreate file with beforeContent.
      // null beforeContent = no snapshot captured; cannot safely recreate.
      if (entry.beforeContent === null) {
        reverted.push({ entry, ok: false, reason: "no before state captured" })
      } else {
        try {
          mkdirSync(dirname(entry.path), { recursive: true })
          writeFileSync(entry.path, entry.beforeContent, "utf8")
          reverted.push({ entry, ok: true })
        } catch (err) {
          reverted.push({
            entry,
            ok: false,
            reason: err instanceof Error ? err.message : String(err),
          })
        }
      }
    } else {
      commandSideEffects.push({
        argv: entry.argv,
        note: "无法自动 undo，需手工 reverse",
      })
    }
  }
  UNDO_CHAIN.delete(chainId)
  UNDO_CHAIN_CONV.delete(chainId)
  return {
    chainId,
    reverted,
    commandSideEffects,
    gitHeadBefore,
  }
}

/**
 * D75 T1 (CQ-003): record undo state for a write_file push. Used by
 * workspace-tools.ts makeWriteFileTool (lines 223-247 before split).
 * Combines single-file undo (UNDO_STACK + touch counter) and chain
 * undo (UNDO_CHAIN) into one call so callers don't need to know about
 * both maps.
 */
export function recordWriteUndo(args: {
  readonly ctx: WorkspaceToolContext
  readonly resolvedPath: string
  readonly beforeContent: string | null
}): void {
  // Single-file undo: push onto per-path stack + touch counter.
  const undoStack = UNDO_STACK.get(args.resolvedPath) ?? []
  undoStack.push(args.beforeContent)
  if (undoStack.length > UNDO_CAP) undoStack.shift()
  UNDO_STACK.set(args.resolvedPath, undoStack)
  UNDO_TOUCH_COUNTER += 1
  UNDO_TOUCHED.set(args.resolvedPath, UNDO_TOUCH_COUNTER)

  // D49 chain push (only if ctx.chainId present).
  if (args.ctx.chainId) {
    let entries = UNDO_CHAIN.get(args.ctx.chainId)
    if (!entries) {
      entries = []
      UNDO_CHAIN.set(args.ctx.chainId, entries)
    }
    entries.push({
      kind: "write",
      path: args.resolvedPath,
      beforeContent: args.beforeContent,
      tool: "write_file",
      pushedAt: UNDO_TOUCH_COUNTER,
    })
    if (entries.length > CHAIN_CAP) entries.shift()
    if (args.ctx.conversationId) {
      UNDO_CHAIN_CONV.set(args.ctx.chainId, args.ctx.conversationId)
    }
  }
}

/** Test-only: snapshot of pushCommandToChain for run_command tool to call. */
export { pushCommandToChain }
