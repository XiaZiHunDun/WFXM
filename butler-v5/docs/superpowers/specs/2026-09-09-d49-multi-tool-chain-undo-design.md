# D49 — Multi-tool Chain 撤销（设计文档）

> 来源：D48 §3.3 结构性 gap（fixture harness 样本盲点，owner 视角下"撤销刚才那 5 步"撞点未触发）。D49 = 提前做（mechanism gap，非 speculative feature）。
>
> 范围：D49 = §3.3 mechanism 修复；D50 = §3.1 partial（audit log / friction / 措辞）单独后续批。
>
> 性质：纯 additive，不改 UNDO_STACK / popMostRecentWrite / undoLastWrite 现有行为（D46 acceptance 锁保护）。

---

## 1. Architecture overview

```
inbound wechat message
    → conversation-loop.ts
       • 每个 inbound message = 1 Run (runId = chainId)
       • workspace-tools ctx.audit.runId 已存在（D47 exec audit）
    → WorkspaceToolContext.audit.runId 透传为 ctx.chainId
    → workspace-tools.ts (extended)
       • write_file.push → UNDO_STACK (existing) + UNDO_CHAIN (NEW)
       • run_command.execute → UNDO_CHAIN (NEW, capture argv/cwd/gitStatusBeforeHash/exit)
       • undoChain(chainId) → ordered revert (NEW)
       • resetUndoChain() (test-only, NEW)
    → wechat-undo-command.ts (extended)
       • 现有: /undo <path>, 中文 NL "撤销刚才" (单写) — 不变
       • 新: chain intent regex → 撤销这轮 / 撤销本次 / 撤销这次 / 撤销这一轮 / /撤销这轮
       • 命中 → undoChain() → 表 + command副作用 list
```

### 关键不变量

- `UNDO_STACK` 行为不变；`popMostRecentWrite` / `undoLastWrite` / `pendingUndoCount` / `resetUndoStack` 全部不变（D46 acceptance lock）
- `chainId = runId`（D47 ExecAuditContext.runId 已 wired，零新 plumbing）
- chain 跨 approval-resume 视为同 chain（同 runId 跨 WaitForApproval cycle 持续）
- 不同 wechat message = 不同 runId = 不同 chain（自动隔离）
- `UNDO_CHAIN` 仅 module-level in-memory，无 cross-restart 持久化（与 UNDO_STACK 同约束）

---

## 2. Components & Data Structures

### 2.1 新增类型（`workspace-tools.ts`）

```typescript
/** Chain = single inbound Run (LLM turn + approval cycles). chainId = runId. */
export type ChainEntry =
  | {
      readonly kind: "write"
      readonly path: string // absolute
      readonly beforeContent: string | null // null = new file
      readonly tool: "write_file"
      readonly pushedAt: number // monotonic counter (= UNDO_TOUCH_COUNTER)
    }
  | {
      readonly kind: "command"
      readonly argv: readonly string[]
      readonly cwd: string
      readonly gitStatusBeforeHash: string | null // git rev-parse HEAD; null if not git / fails
      readonly exit: number | null
      readonly startedAt: number
      readonly tool: "run_command"
    }

/** chainId → ChainEntry[] (insertion order). Module-level, per-process. */
const UNDO_CHAIN = new Map<string, ChainEntry[]>()

/** chainId → conversationId (for cross-conversation guard). */
const UNDO_CHAIN_CONV = new Map<string, string>()

const CHAIN_CAP = 32 // bound memory: 32 entries per chain
```

### 2.2 Push 行为

**`write_file`** — 在原 UNDO_STACK push 之后同步 push UNDO_CHAIN：

```typescript
// existing (D46):
undoStack.push(beforeContent)
UNDO_TOUCH_COUNTER += 1
UNDO_TOUCHED.set(resolved.path, UNDO_TOUCH_COUNTER)

// NEW (D49):
if (ctx.chainId) {
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) { entries = []; UNDO_CHAIN.set(ctx.chainId, entries) }
  entries.push({
    kind: "write",
    path: resolved.path,
    beforeContent,
    tool: "write_file",
    pushedAt: UNDO_TOUCH_COUNTER,
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId ?? "")
}
```

**`run_command`** — execute 后（success/failed 都 push）：

```typescript
// after existing executeArgvInSandbox or spawnCaptured
if (ctx.chainId) {
  let entries = UNDO_CHAIN.get(ctx.chainId)
  if (!entries) { entries = []; UNDO_CHAIN.set(ctx.chainId, entries) }
  entries.push({
    kind: "command",
    argv,
    cwd,
    gitStatusBeforeHash: await safeGitHead(cwd),
    exit: result?.exitCode ?? null,
    startedAt: started,
    tool: "run_command",
  })
  if (entries.length > CHAIN_CAP) entries.shift()
  UNDO_CHAIN_CONV.set(ctx.chainId, ctx.conversationId ?? "")
}
```

`safeGitHead(cwd)` = try `git -C<cwd> rev-parse HEAD`（已在 ALLOWED_RUN_COMMANDS），catch all → null。

### 2.3 Pop / Restore 函数

```typescript
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

export function undoChain(chainId: string): ChainRevertResult | undefined
export function resetUndoChain(): void // test-only
```

### 2.4 `WorkspaceToolContext` 扩展

```typescript
export interface WorkspaceToolContext {
  // ... existing fields
  /** D49: chainId = runId (D47 ExecAuditContext.runId). Undefined = legacy/no-chain mode. */
  readonly chainId?: string
  /** D49: conversationId for chain↔conversation guard. */
  readonly conversationId?: string
}
```

**wiring 约定**：callers (e.g. `wiring.ts`) 应将 `audit.runId` 映射到 `ctx.chainId`、`audit.conversationId` 映射到 `ctx.conversationId`。这是单一来源 (single source of truth)，避免两套值漂移。

---

## 3. Data Flow

### 3.1 Write/Command Push Flow

```
inbound message → conversation-loop → executeToolThroughBoundary
                                       ↓ workspace-tools(ctx.audit.runId → chainId)
                                       ↓
                            write_file.run(args) {
                              beforeContent = readFileSync or null
                              UNDO_STACK[path].push(beforeContent)
                              UNDO_TOUCH_COUNTER += 1
                              UNDO_TOUCHED[path] = UNDO_TOUCH_COUNTER
                              if (ctx.chainId) UNDO_CHAIN[chainId].push({ kind: "write", ... })
                              writeFileSync (sandbox tee or fallback)
                            }

                            run_command.run(args) {
                              argv = ...; check allowlist; inject creds
                              executeArgvInSandbox / spawnCaptured
                              if (ctx.chainId) UNDO_CHAIN[chainId].push({ kind: "command", argv, cwd, gitStatusBeforeHash, exit, ... })
                              return result
                            }
```

**关键**：write_file push 在 execute 之前（已有顺序）；command push 在 execute 之后（capture 真实 exit / stdout）。两条 push 路径在 `WorkspaceToolContext` 同时有 `chainId` 时并行写入。

### 3.2 Chain Undo Trigger Flow

```
inbound message: "撤销这轮"
   ↓
wechat-inbound-llm / wechat-inbound-commands
   ↓
tryWechatUndoCommand(content="撤销这轮") {
   CHAIN_INTENT_REGEX match? 否 → return null (走 LLM 路径)
   rest = ""
   isExplicit? false (no slash prefix)
   rest.length === 0 && !isExplicit → chain undo 分支 (NEW)
   ↓
   recentChainId = findRecentChainIdForConversation(conversationId)
   if !recentChainId → done("当前没有可撤销的轮次。")
   if UNDO_CHAIN_CONV[recentChainId] !== conversationId → done("该轮次不属于当前对话。")
   result = undoChain(recentChainId)
   if !result → done("当前轮次没有可撤销的操作。")
   ↓
   formatChainReply(result) → 表 + command副作用 list
}

tryWechatUndoCommand(content="/undo helper.ts") {
   existing path: undoLastWrite(workspaceRoot, "helper.ts") // 不变
}
```

`findRecentChainIdForConversation(conversationId)` = `for (const [cid, conv] of UNDO_CHAIN_CONV) if (conv === conversationId) return cid`（取最近一次）。

**fallback 行为**：当 caller 不传 conversationId（legacy path / 单对话场景）→ 退化为取最近 chainId（`for UNDO_CHAIN.keys() return last`）。当 conversationId 传了但 `UNDO_CHAIN_CONV` 没记录 → 同样退化为最近 chainId；进入 `undoChain` 前再判 cross-conversation 边界（§4.2）。

### 3.3 Reply 格式

```
[撤销轮次 chainId=abc123]
✅ apps/api/src/helper.ts → 还原为上版
✅ tests/acceptance/foo.test.ts → 还原为上版
❌ apps/api/src/new.ts → 新建文件，已置空（writeFileSync 失败: EACCES）

以下 2 个命令副作用需手工 reverse（无法自动 undo）：
• pnpm install lodash (exit=0)
• git add apps/api/src/helper.ts   (exit=0)

git起点: a1b2c3d（undo 前 HEAD）
```

3 列对齐 mobile readability（D48 §4.2 v7 baseline 已 ship）。`git起点` 行仅在 `gitHeadBefore !== null` 时显示。

### 3.4 Chain intent regex（最长匹配）

```typescript
const CHAIN_INTENT_REGEX =
  /^(撤销这一轮|撤销这轮|撤销本次|撤销这次|\/撤销这轮)\s*$/i

// 在 tryWechatUndoCommand 中顺序：先试 CHAIN_INTENT_REGEX，再试 UNDO_INTENT_REGEX
```

---

## 4. Error Handling

### 4.1 Partial Revert

```
undoChain(chainId):
  entries = UNDO_CHAIN.get(chainId)
    if !entries || entries.length === 0 → return undefined
    ↓
    walk entries REVERSE order (last-pushed first, matches D46 popMostRecentWrite 语义)
    ↓
    for entry in reversed(entries):
      switch entry.kind:
        case "write":
          try writeFileSync(entry.path, entry.beforeContent ?? "")
          catch err: reverted.push({ entry, ok: false, reason: err.message })
        case "command":
          commandSideEffects.push({ argv, note: "无法自动 undo，需手工 reverse" })
    ↓
    DELETE UNDO_CHAIN[chainId]   // chain consumed even on partial failure
    DELETE UNDO_CHAIN_CONV[chainId]
    return { chainId, reverted, commandSideEffects, gitHeadBefore }
```

**关键**：chain 一次性消费（pop 后 DELETE），不能 undo undo。owner 想再 undo 只能针对更早 chain。

### 4.2 Chain 找不到 / 已消费

| 场景 | 回复 |
|---|---|
| UNDO_CHAIN 没有 chainId | "没有可撤销的轮次。" |
| UNDO_CHAIN[chainId] 空数组 | "当前轮次没有可撤销的操作。" |
| UNDO_CHAIN_CONV[chainId] ≠ 当前 conversation | "该轮次不属于当前对话。" |
| `safeGitHead` 失败 | gitStatusBeforeHash = null，commandSideEffects note 不含 git ref（不阻塞） |

### 4.3 Write Revert 失败处理

- 文件已不存在（owner 手工 rm）→ `writeFileSync` 抛 ENOENT → 记 `ok: false, reason: "ENOENT"` → 继续
- 权限变了 → EACCES → 记 reason → 继续
- 内容是 null（新文件）+ revert 失败 → 记 reason（writeFileSync 写空串本身可能 fail） → 不阻塞同 chain 其他 entry
- 路径在 sandbox 外（write 时已 enforce，理论不可达）→ throw → catch 记 reason

### 4.4 Chain Push 失败处理

- `UNDO_CHAIN.set` 自身不会失败（in-memory Map）→ 无 try/catch
- `safeGitHead` 抛错 → catch → null
- chainId 缺失（ctx.chainId undefined）→ 跳过 chain push（仅写 UNDO_STACK，与 D46 现状兼容）

### 4.5 Chain Undo 跨进程 / 重启

- UNDO_CHAIN 是 module-level Map（in-memory），无 cross-restart 持久化
- 进程重启 = UNDO_CHAIN 全清 → chain undo 失效
- owner 可 `git diff` 查 pending changes（已有 comment）
- D46 已承认此限制；D49 不引入新持久化层

---

## 5. Testing

### 5.1 Acceptance cases — chain logic (4 unit)

**File**: `apps/api/src/workspace-tools.chain-undo.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **C1. write-only chain push** | chainId="run1", 2 次 write_file | UNDO_CHAIN["run1"].length === 2, both `kind: "write"`, paths 正确；UNDO_CHAIN_CONV["run1"] === conv |
| **C2. mixed write + command push** | chainId="run1", write + run_command + write | UNDO_CHAIN["run1"].length === 3, second write 在最后；command entry 含 argv/cwd/gitStatusBeforeHash=null（test 目录非 git） |
| **C3. undoChain 顺序 + best-effort** | chainId="run1" 3 write，其中第 2 个 revert 抛 ENOENT（file 手工删） | reverted 长度 === 3；reverted[0] ✅，reverted[1] ❌ reason 含 "ENOENT"，reverted[2] ✅；UNDO_CHAIN["run1"] 已 DELETE（一次性消费）；commandSideEffects 含 chain 中 command entry 的 argv |
| **C4. resetUndoChain** | push 3 chain, resetUndoChain() | UNDO_CHAIN.size === 0；UNDO_CHAIN_CONV.size === 0 |

### 5.2 Intent + Reply cases (4 unit)

**File**: `apps/api/src/wechat-undo-command.chain.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **C5. chain 短语正则匹配** | 5 个短语: `撤销这轮` `撤销本次` `撤销这次` `撤销这一轮` `/撤销这轮`（大小写、尾随空格变体） | 全部被 `tryWechatUndoCommand` 命中并走 chain 分支 |
| **C6. chain undo 无 chain** | UNDO_CHAIN 空 | reply === "没有可撤销的轮次。" |
| **C7. chain undo 成功表格式** | chainId="run1" 含 2 write + 1 command (pnpm install lodash)，conversation 匹配 | reply 含 ✅ 行 ×2、❌ 行 0、command 副作用 list 含 pnpm install argv；gitStatusBeforeHash=null 时不显示 "git起点" 行 |
| **C8. 跨对话 chain 拒绝** | UNDO_CHAIN_CONV["run1"] = convA，当前 conv=B | reply === "该轮次不属于当前对话。" |

### 5.3 Realistic scenario (1 case extension)

**File**: `tests/acceptance/scenarios/_fixtures.ts` 加 D1-chain-extension（不新增 D-number，扩展现有 D1 fixture）

D1 原 scenario: "写 → 跑 test → 失败 → 修 → 再跑" 5 步。

**D1-chain-extension**:
1. setup: 在测试 fixture 中直接调 `UNDO_CHAIN.set("run-d1", [...])` 模拟 5 步真实链（绕开 write_file.run / run_command.run 调用，纯测 popChain + formatChainReply 集成）。这是 acceptance harness 的 mock 模式，与 D46 `resetUndoStack` 一致。
2. owner: "撤销这轮"
3. expect: reply 含 ✅ ×3（3 次 write_file revert），command 副作用 list 含 2 个 `pnpm test` argv；helper.ts 还原为 step 1 前内容；test.ts 还原为 step 2 前内容；第二个 helper.ts 还原为 step 4 前内容（中间 step 1 helper.ts 内容）
4. 实际 fs 检查: 文件内容与 step 0 一致

### 5.4 不破现有 regression

- D46 `popMostRecentWrite` / `undoLastWrite` / `tryWechatUndoCommand` 单写路径测试全部跑过
- C9 fixture drift `resetUndoStack` 不动；新增 `resetUndoChain` 配套用
- 现有 35 realistic scenarios + D44/D46 acceptance 全部跑过

### 5.5 验收指标

- 全 new tests pass (8 unit + 1 realistic extension)
- 全 35/35 realistic pass (no regression)
- 全 1848/1849 + 1 skipped pass (no regression on D46 baseline)
- 0 lint error
- 0 LLM call (纯 mechanism，纯逻辑层)

---

## 6. Files Changed (预估)

| 类型 | 路径 | 改动 |
|---|---|---|
| 改 | `apps/api/src/workspace-tools.ts` | + UNDO_CHAIN / UNDO_CHAIN_CONV / safeGitHead / undoChain / resetUndoChain; + WorkspaceToolContext.chainId+conversationId; write_file + run_command push |
| 改 | `apps/api/src/wechat-undo-command.ts` | + CHAIN_INTENT_REGEX; chain 分支; formatChainReply |
| 改 | `apps/api/src/wiring.ts` (or existing wire path) | 透传 chainId + conversationId 到 WorkspaceToolContext |
| 新 | `apps/api/src/workspace-tools.chain-undo.test.ts` | 4 unit |
| 新 | `apps/api/src/wechat-undo-command.chain.test.ts` | 4 unit |
| 改 | `tests/acceptance/scenarios/_fixtures.ts` | + D1-chain-extension |

预估 +200/-30 行（非最终）；0 业务逻辑改动到现有 UNDO_STACK 路径。

---

## 7. v5 DESIGN alignment

- §7.1 Ports: 不引入新 Port（仅扩 workspace-tools 内部数据）
- §10.4 Sandbox: chain push 不影响 sandbox；command capture 走既有 executeArgvInSandbox / spawnCaptured
- §11.3 Approval: chain 跨 WaitForApproval cycle 同 chain（同 runId），无需 approval 改动
- §12 Knowledge: 不涉及 durable memory / candidate
- §18 Trigger guard: 提前做（mechanism gap，owner 撞点协议不适用 D48 §3.3）

---

## 8. Lessons / 注意事项

- 复用 D46 `resetUndoStack` 模式，新增 `resetUndoChain` 配套 test isolation
- CHAIN_INTENT_REGEX 必须在 UNDO_INTENT_REGEX 之前试（"撤销这轮" 命中 chain，"撤销" 命中单写向后兼容）
- write_file push 与 chain push 顺序：先 UNDO_STACK（保持 D46），再 UNDO_CHAIN（新增）
- run_command push 必须在 execute 之后（capture 真实 exit）；不要在 execute 之前 push

---

**End D49 design doc.**