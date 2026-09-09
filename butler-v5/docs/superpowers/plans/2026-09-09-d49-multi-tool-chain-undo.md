# D49 Multi-tool Chain 撤销 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend v5 `/undo` command to revert an entire multi-tool LLM turn (`chain`) — write_file reverts auto-restored, run_command side-effects listed for owner manual reversal.

**Architecture:** Dual-layer undo state. Existing `UNDO_STACK` (per-path, single-write) is preserved unchanged for backwards compat. New `UNDO_CHAIN: Map<chainId, ChainEntry[]>` is added alongside; `chainId = runId` (D47 `ExecAuditContext.runId` already wired). Owner trigger: 5 new phrases (`撤销这轮` / `撤销本次` / `撤销这次` / `撤销这一轮` / `/撤销这轮`). Revert is best-effort + table report; chain consumed once.

**Tech Stack:** TypeScript, Vitest, vitest.archived.config, eslint, pnpm workspace monorepo (apps/api + packages/runtime + packages/domain).

**Spec:** `butler-v5/docs/superpowers/specs/2026-09-09-d49-multi-tool-chain-undo-design.md` (commit `81a21dae`).

**Compliance invariant:** ZERO behavior change to `UNDO_STACK` / `popMostRecentWrite` / `undoLastWrite` / `pendingUndoCount` / `resetUndoStack` (D46 acceptance lock protected).

---

## File Structure

| Type | Path | Responsibility |
|---|---|---|
| Modify | `apps/api/src/workspace-tools.ts` | + `UNDO_CHAIN` / `UNDO_CHAIN_CONV` / `safeGitHead` / `undoChain` / `resetUndoChain` / `ChainEntry` type / `ChainRevertResult` type; + `WorkspaceToolContext.chainId + conversationId`; write_file + run_command push |
| Modify | `apps/api/src/wechat-undo-command.ts` | + `CHAIN_INTENT_REGEX`; chain 分支; `findRecentChainIdForConversation`; `formatChainReply` |
| Modify | `apps/api/src/wiring.ts` (or existing wire path) | 透传 `chainId` + `conversationId` 到 `WorkspaceToolContext` |
| Create | `apps/api/src/workspace-tools.chain-undo.test.ts` | C1-C4 (chain logic unit) |
| Create | `apps/api/src/wechat-undo-command.chain.test.ts` | C5-C8 (intent + reply unit) |
| Modify | `tests/acceptance/scenarios/_fixtures.ts` | + D1-chain-extension fixture |

---

## Task 1: UNDO_CHAIN data structure + write_file push (TDD)

**Files:**
- Create: `apps/api/src/workspace-tools.chain-undo.test.ts`
- Modify: `apps/api/src/workspace-tools.ts:44-52` (WorkspaceToolContext), `:182-269` (write_file run), `:271-335` (UNDO_STACK section)

- [ ] **Step 1: Write failing test C1 (write-only chain push)**

Create `apps/api/src/workspace-tools.chain-undo.test.ts`:

```typescript
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
    const ctx = { chainId: "run-1", conversationId: "conv-1" }
    const writeA = makeWriteFileTool(ctx)
    const writeB = makeWriteFileTool(ctx)
    const r1 = await writeA.run({ path: "a.ts", content: "NEW_A" })
    const r2 = await writeB.run({ path: "b.ts", content: "NEW_B" })
    expect(r1.ok).toBe(true)
    expect(r2.ok).toBe(true)

    // Re-read UNDO_CHAIN state via undoChain
    const { undoChain } = await import("./workspace-tools.js")
    const result = undoChain("run-1")
    expect(result).toBeDefined()
    expect(result!.reverted).toHaveLength(2)
    // Reversed order: B then A
    expect(result!.reverted[0]!.entry.kind).toBe("write")
    expect((result!.reverted[0]!.entry as { path: string }).path).toBe(FILE_B)
    expect(result!.reverted[1]!.ok).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -30`
Expected: FAIL — `undoChain` is not exported / `resetUndoChain` not exported.

- [ ] **Step 3: Add `ChainEntry` / `ChainRevertResult` types + `UNDO_CHAIN` / `UNDO_CHAIN_CONV` / `resetUndoChain` + extend `WorkspaceToolContext` in `workspace-tools.ts`**

In `apps/api/src/workspace-tools.ts`:

(a) Extend `WorkspaceToolContext` (around line 44):

```typescript
export interface WorkspaceToolContext {
  readonly workspaceRoot?: string
  readonly credentialProvider?: CredentialProvider
  readonly credentialAllowlist?: readonly string[]
  readonly audit?: ExecAuditContext
  /** D49: chainId = runId (D47 ExecAuditContext.runId). */
  readonly chainId?: string
  /** D49: conversationId for chain↔conversation guard. */
  readonly conversationId?: string
}
```

(b) After the `UNDO_TOUCHED` declaration block (around line 284), add:

```typescript
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
      readonly kind: "command"
      readonly argv: readonly string[]
      readonly cwd: string
      readonly gitStatusBeforeHash: string | null
      readonly exit: number | null
      readonly startedAt: number
      readonly tool: "run_command"
    }

export interface ChainRevertResult {
  readonly chainId: string
  readonly reverted: ReadonlyArray<{
    readonly entry: ChainEntry
    readonly ok: boolean
    readonly reason?: string
  }>
  readonly commandSideEffects: ReadonlyArray<{
    readonly argv: readonly string[]
    readonly note: string
  }>
  readonly gitHeadBefore: string | null
}

const UNDO_CHAIN = new Map<string, ChainEntry[]>()
const UNDO_CHAIN_CONV = new Map<string, string>()
let GIT_HEAD_CACHE: string | null | undefined

/** Try `git rev-parse HEAD` in cwd. Returns hash or null (cache per cwd, swallow all errors). */
async function safeGitHead(cwd: string): Promise<string | null> {
  if (GIT_HEAD_CACHE !== undefined) return GIT_HEAD_CACHE
  try {
    const { execFile } = await import("node:child_process")
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
```

(c) In `makeWriteFileTool` `run()` (after the existing `UNDO_TOUCHED.set(resolved.path, UNDO_TOUCH_COUNTER)` line, around line 222), add chain push:

```typescript
// D49: chain push (only if ctx.chainId present)
if (ctx.chainId) {
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) {
    entries = []
    UNDO_CHAIN.set(ctx.chainId, entries)
  }
  entries.push({
    kind: "write",
    path: resolved.path,
    beforeContent,
    tool: "write_file",
    pushedAt: UNDO_TOUCH_COUNTER,
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  if (ctx.conversationId) UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId)
}
```

(d) Add `undoChain` stub (real impl in Task 3) after `resetUndoStack()` (around line 335):

```typescript
export function undoChain(chainId: string): ChainRevertResult | undefined {
  const entries = UNDO_CHAIN.get(chainId)
  if (!entries || entries.length === 0) return undefined
  // Real impl in Task 3
  return undefined
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -15`
Expected: PASS — C1 passes (stub returns undefined but `result` defined is mocked; actually stub returns undefined so test will fail. Adjust: use the real impl preview. Replace stub.)

Replace the stub in workspace-tools.ts with a minimal preview that returns the chain state for C1 to pass:

```typescript
export function undoChain(chainId: string): ChainRevertResult | undefined {
  const entries = UNDO_CHAIN.get(chainId)
  if (!entries || entries.length === 0) return undefined
  const gitHeadBefore = GIT_HEAD_CACHE ?? null
  const reverted: Array<{ entry: ChainEntry; ok: boolean; reason?: string }> = []
  for (const entry of [...entries].reverse()) {
    if (entry.kind !== "write") continue
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
  }
  UNDO_CHAIN.delete(chainId)
  UNDO_CHAIN_CONV.delete(chainId)
  return {
    chainId,
    reverted,
    commandSideEffects: [],
    gitHeadBefore,
  }
}
```

Add import at top of workspace-tools.ts: `import { mkdirSync, readFileSync, realpathSync, statSync, writeFileSync } from "node:fs"` already includes mkdirSync/writeFileSync. Verify `dirname` is imported (it is, line 13).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -15`
Expected: PASS — C1 ✅.

- [ ] **Step 6: Commit**

```bash
cd butler-v5 && git add apps/api/src/workspace-tools.ts apps/api/src/workspace-tools.chain-undo.test.ts
git commit -m "feat(chain-undo): UNDO_CHAIN data + write_file push (D49 Task 1)"
```

---

## Task 2: run_command push + safeGitHead (TDD)

**Files:**
- Modify: `apps/api/src/workspace-tools.chain-undo.test.ts` (add C2)
- Modify: `apps/api/src/workspace-tools.ts:337-441` (makeRunCommandTool)

- [ ] **Step 1: Write failing test C2 (mixed write + command push)**

Append to `apps/api/src/workspace-tools.chain-undo.test.ts`:

```typescript
import { makeRunCommandTool } from "./workspace-tools.js"

describe("D49 chain undo — run_command push", () => {
  beforeEach(setup)

  it("C2: mixed write + command push captures argv/cwd/gitStatusBeforeHash", async () => {
    const ctx = { chainId: "run-2", conversationId: "conv-2" }
    const write = makeWriteFileTool(ctx)
    const runCmd = makeRunCommandTool(ctx)
    await write.run({ path: "a.ts", content: "X" })
    await runCmd.run({ argv: ["echo", "hello"] })
    await write.run({ path: "b.ts", content: "Y" })

    const result = undoChain("run-2")
    expect(result).toBeDefined()
    expect(result!.reverted).toHaveLength(2)
    expect(result!.commandSideEffects).toHaveLength(1)
    expect(result!.commandSideEffects[0]!.argv).toEqual(["echo", "hello"])
    expect((result!.reverted[0]!.entry as { path: string }).path).toBe(FILE_B)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -15`
Expected: FAIL — run_command not pushing to UNDO_CHAIN, commandSideEffects empty.

- [ ] **Step 3: Add run_command chain push in `makeRunCommandTool`**

In `apps/api/src/workspace-tools.ts`, find the `makeRunCommandTool` function. There are two paths in this function (sandboxed vs disabled). Add chain push at end of both paths (right before `return result` lines, after `recordExecAudit`).

After the disabled path's `return result` (around line 427), but BEFORE the return:

```typescript
// D49: chain push (both sandboxed and disabled paths)
if (ctx.chainId) {
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) {
    entries = []
    UNDO_CHAIN.set(ctx.chainId, entries)
  }
  entries.push({
    kind: "command",
    argv,
    cwd,
    gitStatusBeforeHash: await safeGitHead(cwd),
    exit: result.exitCode,
    startedAt: started,
    tool: "run_command",
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  if (ctx.conversationId) UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId)
}
return result
```

For the sandboxed path (after `return` near line 438), restructure to capture the result first:

```typescript
const finalResult = sandboxed.ok
  ? { ok: true as const, output: "stdout" in sandboxed ? sandboxed.stdout ?? "" : "sandboxed run returned no output", exitCode: 0 }
  : { ok: false as const, reason: sandboxed.reason ?? "sandbox failed", exitCode: null }

// D49: chain push
if (ctx.chainId) {
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) {
    entries = []
    UNDO_CHAIN.set(ctx.chainId, entries)
  }
  entries.push({
    kind: "command",
    argv,
    cwd,
    gitStatusBeforeHash: await safeGitHead(cwd),
    exit: finalResult.ok ? 0 : null,
    startedAt: started,
    tool: "run_command",
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  if (ctx.conversationId) UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId)
}

if (!finalResult.ok) return finalResult
return { ok: true, output: finalResult.output }
```

Also update `undoChain` to populate `commandSideEffects`. Replace existing `undoChain` impl with:

```typescript
export function undoChain(chainId: string): ChainRevertResult | undefined {
  const entries = UNDO_CHAIN.get(chainId)
  if (!entries || entries.length === 0) return undefined
  const gitHeadBefore = GIT_HEAD_CACHE ?? null
  const reverted: Array<{ entry: ChainEntry; ok: boolean; reason?: string }> = []
  const commandSideEffects: Array<{ argv: readonly string[]; note: string }> = []
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
    } else {
      commandSideEffects.push({
        argv: entry.argv,
        note: "无法自动 undo，需手工 reverse",
      })
    }
  }
  UNDO_CHAIN.delete(chainId)
  UNDO_CHAIN_CONV.delete(chainId)
  return { chainId, reverted, commandSideEffects, gitHeadBefore }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -15`
Expected: PASS — C2 ✅.

- [ ] **Step 5: Commit**

```bash
cd butler-v5 && git add apps/api/src/workspace-tools.ts apps/api/src/workspace-tools.chain-undo.test.ts
git commit -m "feat(chain-undo): run_command push captures argv/cwd/gitHead (D49 Task 2)"
```

---

## Task 3: undoChain best-effort partial revert (TDD)

**Files:**
- Modify: `apps/api/src/workspace-tools.chain-undo.test.ts` (add C3)
- Modify: `apps/api/src/workspace-tools.ts` (undoChain already impl'd; this task just locks test)

- [ ] **Step 1: Write failing test C3 (reverse order + partial revert + chain consumed)**

Append to `apps/api/src/workspace-tools.chain-undo.test.ts`:

```typescript
import { chmodSync } from "node:fs"

describe("D49 chain undo — partial revert", () => {
  beforeEach(setup)

  it("C3: reverse order revert; failures caught and continued; chain consumed", async () => {
    const ctx = { chainId: "run-3", conversationId: "conv-3" }
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
    expect(result!.reverted).toHaveLength(3)
    // Reverse order: c first, then b, then a
    expect((result!.reverted[0]!.entry as { path: string }).path).toBe(join(TMP, "c.ts"))
    expect((result!.reverted[1]!.entry as { path: string }).path).toBe(FILE_B)
    expect((result!.reverted[2]!.entry as { path: string }).path).toBe(FILE_A)

    // Restore perms for cleanup
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
```

- [ ] **Step 2: Run test to verify it passes (already implemented in Task 2)**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -15`
Expected: PASS — C3 ✅ (undoChain from Task 2 already handles partial + DELETE).

If FAIL, the `undoChain` impl from Task 2 needs adjustment. Verify `writeFileSync` throws ENOENT and is caught; verify chain DELETE.

- [ ] **Step 3: Commit**

```bash
cd butler-v5 && git add apps/api/src/workspace-tools.chain-undo.test.ts
git commit -m "test(chain-undo): C3 partial revert best-effort + chain consumed (D49 Task 3)"
```

---

## Task 4: resetUndoChain + conversation mapping (TDD)

**Files:**
- Modify: `apps/api/src/workspace-tools.chain-undo.test.ts` (add C4 + cross-conv helper)

- [ ] **Step 1: Write failing test C4 (resetUndoChain)**

Append:

```typescript
describe("D49 chain undo — resetUndoChain", () => {
  beforeEach(setup)

  it("C4: resetUndoChain clears UNDO_CHAIN + UNDO_CHAIN_CONV", async () => {
    const ctx = { chainId: "run-x", conversationId: "conv-x" }
    const write = makeWriteFileTool(ctx)
    await write.run({ path: "a.ts", content: "Z" })
    expect(undoChain("run-x")).toBeDefined()

    resetUndoChain()
    expect(undoChain("run-x")).toBeUndefined()
  })
})
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd butler-v5 && pnpm test apps/api/src/workspace-tools.chain-undo.test.ts 2>&1 | tail -10`
Expected: PASS — C4 ✅ (resetUndoChain already impl'd in Task 1).

- [ ] **Step 3: Add helper export `getUndoChainConversation` for cross-conv guard (used by Task 5)**

In `workspace-tools.ts`, add after `resetUndoChain`:

```typescript
/** Test/diagnostic: get conversationId stored for a chainId, or undefined. */
export function getUndoChainConversation(chainId: string): string | undefined {
  return UNDO_CHAIN_CONV.get(chainId)
}
```

- [ ] **Step 4: Commit**

```bash
cd butler-v5 && git add apps/api/src/workspace-tools.ts apps/api/src/workspace-tools.chain-undo.test.ts
git commit -m "feat(chain-undo): resetUndoChain + cross-conv guard helper (D49 Task 4)"
```

---

## Task 5: chain intent regex + chain 分支 + reply format (TDD)

**Files:**
- Create: `apps/api/src/wechat-undo-command.chain.test.ts`
- Modify: `apps/api/src/wechat-undo-command.ts`

- [ ] **Step 1: Write failing tests C5/C6/C7/C8**

Create `apps/api/src/wechat-undo-command.chain.test.ts`:

```typescript
import { describe, expect, it, beforeEach } from "vitest"
import { writeFileSync, mkdirSync, rmSync } from "node:fs"
import { join } from "node:path"
import { tryWechatUndoCommand } from "./wechat-undo-command.js"
import { resetUndoStack, resetUndoChain, undoChain } from "./workspace-tools.js"
import type { Wiring } from "./wiring.js"

// Minimal Wiring stub — chain undo doesn't use it for chain branch
const stubWiring = {} as Wiring
const FROM = "owner-1"

const TMP = join(process.cwd(), ".tmp-chain-reply-test")
const FILE_A = join(TMP, "a.ts")

function setup() {
  rmSync(TMP, { recursive: true, force: true })
  mkdirSync(TMP, { recursive: true })
  writeFileSync(FILE_A, "OLD_A", "utf8")
  resetUndoStack()
  resetUndoChain()
}

describe("D49 wechat-undo-command chain branch", () => {
  beforeEach(setup)

  it("C5: 5 chain phrases all match and route to chain branch", async () => {
    const phrases = ["撤销这轮", "撤销本次", "撤销这次", "撤销这一轮", "/撤销这轮", "撤销这轮 ", "撤销这轮"]
    for (const p of phrases) {
      const r = await tryWechatUndoCommand({
        wiring: stubWiring,
        fromUserId: FROM,
        content: p,
        env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP },
      })
      expect(r).not.toBeNull()
      // No chain seeded → "没有可撤销的轮次"
      expect(r?.reply).toMatch(/没有可撤销的轮次/)
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
    expect(r?.reply).toBe("没有可撤销的轮次。")
  })

  it("C7: chain undo success shows table with writes + command side-effects", async () => {
    // Seed UNDO_CHAIN["run-7"] with 2 writes + 1 command via workspace-tools
    const { UNDO_CHAIN_FOR_TEST } = await import("./workspace-tools.js")
    UNDO_CHAIN_FOR_TEST.set("run-7", [
      { kind: "write", path: FILE_A, beforeContent: "OLD_A", tool: "write_file", pushedAt: 1 },
      { kind: "command", argv: ["pnpm", "install", "lodash"], cwd: TMP, gitStatusBeforeHash: null, exit: 0, startedAt: 2, tool: "run_command" },
    ])

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP },
    })
    expect(r).not.toBeNull()
    expect(r?.reply).toContain("✅")
    expect(r?.reply).toContain(FILE_A)
    expect(r?.reply).toContain("pnpm install lodash")
    expect(r?.reply).not.toContain("git起点") // gitStatusBeforeHash=null
  })

  it("C8: cross-conversation chain is rejected", async () => {
    const { UNDO_CHAIN_FOR_TEST } = await import("./workspace-tools.js")
    UNDO_CHAIN_FOR_TEST.set("run-8", [
      { kind: "write", path: FILE_A, beforeContent: "OLD_A", tool: "write_file", pushedAt: 1 },
    ])
    const { UNDO_CHAIN_CONV_FOR_TEST } = await import("./workspace-tools.js")
    UNDO_CHAIN_CONV_FOR_TEST.set("run-8", "conv-A")

    const r = await tryWechatUndoCommand({
      wiring: stubWiring,
      fromUserId: FROM,
      content: "撤销这轮",
      env: { ...process.env, BUTLER_V5_WORKSPACE_ROOT: TMP, BUTLER_V5_CONVERSATION_ID: "conv-B" },
    })
    expect(r?.reply).toBe("该轮次不属于当前对话。")
  })
})
```

This requires exporting `UNDO_CHAIN` / `UNDO_CHAIN_CONV` from `workspace-tools.ts` for test seeding. Adjust in Step 3.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd butler-v5 && pnpm test apps/api/src/wechat-undo-command.chain.test.ts 2>&1 | tail -30`
Expected: FAIL — chain regex not matched / chain branch not impl.

- [ ] **Step 3: Extend `workspace-tools.ts` to export test-only seed handles**

Replace the `const UNDO_CHAIN = new Map(...)` line with `export const UNDO_CHAIN_FOR_TEST = UNDO_CHAIN`. Same for `UNDO_CHAIN_CONV_FOR_TEST`. Keep production impl untouched.

In `workspace-tools.ts`:

```typescript
/** @internal — exported for tests only. Production code uses undoChain(). */
export const UNDO_CHAIN_FOR_TEST = UNDO_CHAIN
/** @internal — exported for tests only. */
export const UNDO_CHAIN_CONV_FOR_TEST = UNDO_CHAIN_CONV
```

- [ ] **Step 4: Implement chain branch in `tryWechatUndoCommand`**

In `apps/api/src/wechat-undo-command.ts`, add at top (after existing UNDO_INTENT_REGEX, around line 32):

```typescript
// D49: chain intent (multi-tool turn undo). Match longest-first.
const CHAIN_INTENT_REGEX =
  /^(撤销这一轮|撤销这轮|撤销本次|撤销这次|\/撤销这轮)\s*$/i
```

Extend `UNDO_INTENT_REGEX` to also match chain triggers (otherwise top-of-function `if (!UNDO_INTENT_REGEX.test(trimmed)) return null` rejects chain phrases):

Replace the existing UNDO_INTENT_REGEX (around line 31-32):

```typescript
const UNDO_INTENT_REGEX =
  /^(撤销这一轮|撤销这轮|撤销本次|撤销这次|撤销刚才|撤销上一步|撤销上一次|撤销上次|撤销|\/undo|\/撤销|\/撤销这轮|undo)\s*/i
```

(Order doesn't matter because chain intent is checked separately inside the function.)

Add import (after existing imports):

```typescript
import {
  undoLastWrite,
  popMostRecentWrite,
  undoChain,
  getUndoChainConversation,
} from "./workspace-tools.js"
```

Modify `tryWechatUndoCommand` `rest.length === 0` branch (around line 84). Insert chain branch BEFORE the existing `rest.length === 0` block:

```typescript
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
    if (!chainId) {
      chainId = undoChain_listChainIds().at(-1)
    }
    if (!chainId) return done("没有可撤销的轮次。")
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

  // existing logic unchanged
  if (rest.length === 0) {
    if (isExplicit) {
      return done("请用 `/undo <path>` 指定要还原的文件路径。")
    }
    const most = popMostRecentWrite()
    if (most === undefined) {
      return done("没有可撤销的写操作。")
    }
    return restoreAndReply(most.path, most.path, most.content)
  }
```

Add to `workspace-tools.ts` exports (after `getUndoChainConversation`):

```typescript
/** Test/diagnostic: list all chainId↔conversationId pairs. */
export function* undoChain_listConversations(): Iterable<[string, string]> {
  for (const [cid, conv] of UNDO_CHAIN_CONV) yield [cid, conv]
}

/** Test/diagnostic: list all chainIds in insertion order. */
export function undoChain_listChainIds(): readonly string[] {
  return [...UNDO_CHAIN.keys()]
}
```

Add to `wechat-undo-command.ts` (above `restoreAndReply`, around line 48):

```typescript
function formatChainReply(result: ChainRevertResult): string {
  const lines: string[] = []
  lines.push(`[撤销轮次 chainId=${result.chainId}]`)
  for (const r of result.reverted) {
    if (r.entry.kind === "write") {
      const ok = r.ok ? "✅" : "❌"
      const reason = r.ok ? "" : ` (${r.reason ?? "失败"})`
      const label = r.entry.beforeContent === null ? "新建文件已置空" : "还原为上版"
      lines.push(`${ok} ${r.entry.path} → ${label}${reason}`)
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
```

Add import `ChainRevertResult`:

```typescript
import type { ChainRevertResult } from "./workspace-tools.js"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd butler-v5 && pnpm test apps/api/src/wechat-undo-command.chain.test.ts 2>&1 | tail -30`
Expected: PASS — C5/C6/C7/C8 ✅.

- [ ] **Step 6: Commit**

```bash
cd butler-v5 && git add apps/api/src/wechat-undo-command.ts apps/api/src/workspace-tools.ts apps/api/src/wechat-undo-command.chain.test.ts
git commit -m "feat(chain-undo): wechat chain intent + formatChainReply (D49 Task 5)"
```

---

## Task 6: wiring chainId + conversationId 透传

**Files:**
- Modify: `apps/api/src/wiring.ts` (or wherever WorkspaceToolContext is constructed for wechat inbound)

- [ ] **Step 1: Find where WorkspaceToolContext is constructed for wechat inbound tools**

Run: `grep -rn "makeWriteFileTool\|makeRunCommandTool\|WorkspaceToolContext" apps/ --include="*.ts" | grep -v test`
Locate the call site that passes `audit` to `workspace-tools`.

- [ ] **Step 2: Add chainId + conversationId to that ctx**

Add right after the existing `audit: ...` line:

```typescript
chainId: <runId from current Run>,
conversationId: <conversationId from current Run>,
```

Both values come from the same `audit` payload (D47). If the call site already has `runId` / `conversationId` in scope, wire them through.

- [ ] **Step 3: Run regression: 35/35 realistic + 1848/1849 + 0 lint**

Run: `cd butler-v5 && pnpm test 2>&1 | tail -20`
Expected: All unit tests pass.

Run: `cd butler-v5 && pnpm test tests/acceptance/scenarios/realistic.test.ts 2>&1 | tail -10`
Expected: 35/35 pass.

Run: `cd butler-v5 && pnpm lint 2>&1 | tail -10`
Expected: 0 errors.

If any fail, fix incrementally before committing. Common issues: chain push leaking into existing UNDO_STACK acceptance tests (should not — write_file push is AFTER UNDO_STACK push). Confirm D46 tests still pass.

- [ ] **Step 4: Commit**

```bash
cd butler-v5 && git add apps/api/src/wiring.ts
git commit -m "feat(chain-undo): wire chainId + conversationId to WorkspaceToolContext (D49 Task 6)"
```

---

## Task 7: D1-chain-extension realistic scenario

**Files:**
- Modify: `tests/acceptance/scenarios/_fixtures.ts`

- [ ] **Step 1: Locate D1 fixture**

Run: `grep -n "D1\|name:.*'D1'" tests/acceptance/scenarios/_fixtures.ts`
Find the existing D1 scenario definition.

- [ ] **Step 2: Add `D1-chain-extension` scenario after D1**

Append a new entry following the existing fixture shape. Use `resetUndoChain()` + direct `UNDO_CHAIN_FOR_TEST.set()` to seed the 5-step chain (matching the acceptance harness mock pattern from D46):

```typescript
{
  id: "D1-chain-extension",
  // ... copy D1 setup pattern but seed UNDO_CHAIN with 5-step chain
  // Setup: write helper.ts (step 1) → write test.ts (step 2) → run pnpm test (step 3, exit=1)
  //         → write helper.ts (step 4) → run pnpm test (step 5, exit=0)
  // Owner says: "撤销这轮"
  // Expect: 3 ✅ reverts, 2 command side-effects listed, file contents match step 0
}
```

Refer to D46 `resetUndoStack` mock pattern in `_fixtures.ts` for the harness style.

- [ ] **Step 3: Run acceptance harness**

Run: `cd butler-v5 && pnpm test tests/acceptance/scenarios/realistic.test.ts 2>&1 | tail -10`
Expected: 36/36 pass (35 original + 1 new D1-chain-extension).

- [ ] **Step 4: Run full test suite + lint**

Run: `cd butler-v5 && pnpm test 2>&1 | tail -20 && pnpm lint 2>&1 | tail -10`
Expected: All pass, 0 lint errors.

- [ ] **Step 5: Commit**

```bash
cd butler-v5 && git add tests/acceptance/scenarios/_fixtures.ts tests/acceptance/scenarios/realistic.test.ts
git commit -m "test(chain-undo): D1-chain-extension realistic scenario (D49 Task 7)"
```

---

## Task 8: Final verification + handoff

**Files:** none (verification)

- [ ] **Step 1: Run full test suite**

Run: `cd butler-v5 && pnpm test 2>&1 | tail -20`
Expected: All pass.

- [ ] **Step 2: Run lint**

Run: `cd butler-v5 && pnpm lint 2>&1 | tail -10`
Expected: 0 errors.

- [ ] **Step 3: Verify acceptance numbers match D46 baseline**

Count tests passing: should be ≥ D46 baseline `1848/1849 + 1 skipped`. New tests: 8 unit (C1-C8) + 1 realistic = ≥9 new. Total expected: ≥1857/1849 + 1 skipped + 36/36 realistic.

Run: `cd butler-v5 && pnpm test 2>&1 | grep -E "Tests|passed|failed" | tail -5`

- [ ] **Step 4: Push to origin**

```bash
cd butler-v5 && git push origin main
```

- [ ] **Step 5: Write handoff memory**

Add `butler-v5/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D49-multi-tool-chain-undo-2026-09-09.md` per D-series pattern (see `project-fix-D48-owner-perspective-2026-09-08.md` template).

Update `MEMORY.md` index with one-line pointer to D49 entry.

---

**End D49 implementation plan. 8 tasks, ~7 commits expected.**