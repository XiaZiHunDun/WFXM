# R2 Domain + Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 Butler v5 Domain 层 + Contract Schema 的全部纯函数基础，覆盖已批准规格 §5/§7/§8；与此同时完成 R1 残留的 test tsconfig 闭环，让 `pnpm gate` 的 lint 段退出码 0。

**Architecture:** 强边界模块化单体 + FC/IS：Domain 全部纯 ADT、状态机、纯函数、Projection；Ports 用 Effect Tag；Application 仅依赖 ports + domain；Adapters 实现副作用。R2 不写任何运行时副作用，只输出可被 R3+ 复用的纯函数与契约。Test tsconfig 闭环把 `tests/` 与各包测试加入 typed rules 覆盖。

**Tech Stack:** TypeScript strict、Node.js 20、pnpm 9、Turborepo、Effect-TS 3、Vitest 1.6、ESLint 8.57、@typescript-eslint 7、ts-prune、Drizzle、PostgreSQL 16 + pgvector。

---

## 范围与执行纪律

### 现状与 R2 边界

R1 结束状态：35 test files / 230 tests passed；typecheck/file-size/protected-files/deadcode 4 项全 PASS；残留两个偏差：lint typed-rules 37 errors + 15 warnings、prettier 缺失。R2 必须以 R1 偏差闭环为入口（不要把偏差带进 R2），主交付物是 Domain + Contracts 的纯函数 + 契约。

### 范围纪律

- 仅修改 `butler-v5/` 内（当前 untracked 目录）的文件，**不允许触碰 v4 主线**（`butler/`、`tests/` 等已 M 项）；
- `butler-v5/.butler/scope-boundaries.json` 列 `off_limits`：`packages/domain/src/errors.ts`、`packages/ports/src/index.ts`、`.cursorrules`、`AGENTS.md`、`.butler/*.json`、`.github/workflows/*`、`.env`、`.env.local`；
- 不得 stage / commit 任何文件；每个 Task 完成后由黑板 shift 卡记录；
- 任何 R1 偏差（prettier / lint 已知失败）需在本计划内消化，不得遗留到 R3。

### 六子项目顺序

```text
R2.0  test tsconfig 闭环 + 领域扫描
  → R2.1 Project + Conversation ADT
  → R2.2 Tools + Workflow + Memory
  → R2.3 Events + ADT 治理
  → R2.4 Contracts Schema
  → R2.5 端到端门禁
```

每子项目可独立验证；前一个未通过不阻塞后一个的设计讨论，但 R2.5 依赖 R2.0–R2.4 的最终输出。

---

## R2.0：test tsconfig 闭环 + 领域扫描

### Task 0.1: 把 tests/ 全部加入 typed rules 覆盖

**Files:**
- Create: `butler-v5/tests/tsconfig.json`
- Modify: `butler-v5/.eslintrc.json`
- Create: `butler-v5/tests/_meta/architecture-typed-rules.test.ts`

- [ ] **Step 1: 创建 tests/tsconfig.json**

```json
{
  "extends": "../tsconfig.base.json",
  "compilerOptions": {
    "noEmit": true,
    "rootDir": "."
  },
  "include": ["./**/*.ts", "../packages/*/src/**/*.ts"]
}
```

- [ ] **Step 2: 修改 `.eslintrc.json` 在 `parserOptions.project` 末尾加入 `tests/tsconfig.json`**

```json
"project": [
  "./packages/*/tsconfig.json",
  "./apps/*/tsconfig.json",
  "./tests/**/tsconfig.json"
]
```

即在数组末尾加 `"tests/tsconfig.json"`，与现有 entries 并列；保持 `tsconfigRootDir: "."` 不变。

- [ ] **Step 3: 写架构门禁测试**

`butler-v5/tests/_meta/architecture-typed-rules.test.ts`：

```typescript
import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("architecture", () => {
  it("eslint typed-rules cover all source test files", () => {
    const out = execFileSync(
      "pnpm",
      ["exec", "eslint", "packages/", "apps/", "tests/", "--ext", ".ts", "--max-warnings", "0"],
      { cwd: process.cwd(), encoding: "utf8" },
    )
    expect(out.length).toBeGreaterThanOrEqual(0)
  })
})
```

- [ ] **Step 4: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 lint 2>&1 | tail -30
echo "lint_exit=$?"
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test tests/_meta/architecture-typed-rules.test.ts
echo "test_exit=$?"
```

Expected: lint exit 0，typed rules 覆盖所有 test 文件后剩余 warnings 全部归 0；架构测试 PASS。

### Task 0.2: 关闭 R1 残留的 prettier 警告

**Files:**
- Modify: `butler-v5/package.json`

- [ ] **Step 1: 修 `format:check` 脚本为不依赖本地 `prettier` 二进制的版本**

修改 `butler-v5/package.json` 中 `format` 与 `format:check`：

```json
"format": "pnpm exec prettier --write .",
"format:check": "pnpm exec prettier --check ."
```

- [ ] **Step 2: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 format:check 2>&1 | tail -20
echo "exit=$?"
```

Expected: exit 0（所有源文件已符合 Prettier 默认规则或无 Prettier 错误）；如失败，记录待修文件清单。

### Task 0.3: 领域现状扫描与门禁完整性验证

**Files:**
- Create: `butler-v5/docs/analysis/r2-domain-snapshot-2026-08-08.md`

- [ ] **Step 1: 扫描现有 domain 包与 ports**

```bash
find /home/ailearn/projects/WFXM/butler-v5/packages/domain/src -name '*.ts' ! -name '*.test.ts' | sort
find /home/ailearn/projects/WFXM/butler-v5/packages/ports/src -name '*.ts' | sort
```

- [ ] **Step 2: 写扫描报告**

`butler-v5/docs/analysis/r2-domain-snapshot-2026-08-08.md` 内容模板：

```markdown
# v5 Domain 现状快照（2026-08-08）

## conversation/
- context.ts, transitions.ts, types.ts, index.ts
- 缺失：Project / Turn 单独 ADT，UserMessage 事件载荷

## memory/
- pure.ts, types.ts, index.ts
- 缺失：Search query schema、recency decay policy、conflict resolution

## permissions/
- types.ts, index.ts
- 缺失：decidePermission 纯函数、Capability Lease ADT

## projects/
- pure.ts, types.ts, index.ts
- 缺失：Project lifecycle 状态机、WorkspaceRoot isolation

## tools/
- pure.ts, types.ts, index.ts
- 缺失：ToolDefinition ADT、CommandSpec 收口

## workflows/
- transitions.ts, types.ts, index.ts
- 缺失：WorkflowRun/Step ADT、Channel 多分支实现

## errors.ts
- 现有 11 种 ButlError 变体；R2 复核是否需要补 Approval/Network

## ports/src/index.ts
- 现有 11 个 Effect Tag；R2 需对齐规格 §6.1/§8.1
```

- [ ] **Step 3: 验证 R0/R1 门禁仍全绿**

```bash
bash /home/ailearn/projects/WFXM/butler-v5/scripts/typecheck-gate.sh
echo "gate_exit=$?"
```

Expected: exit 0。

### R2.0 退出条件

- `pnpm lint` 退出码 0
- `pnpm format:check` 退出码 0
- `pnpm test` 退出码 0
- typecheck-gate 退出码 0
- `r2-domain-snapshot-2026-08-08.md` 已落盘

---

## R2.1: Project + Conversation 完整 ADT

### Task 1.1: 扩展 Project 状态机

**Files:**
- Modify: `butler-v5/packages/domain/src/projects/types.ts`
- Modify: `butler-v5/packages/domain/src/projects/pure.ts`
- Modify: `butler-v5/packages/domain/src/projects/index.ts`
- Modify: `butler-v5/packages/domain/src/projects/pure.test.ts`

- [ ] **Step 1: 写失败测试**

在 `pure.test.ts` 末尾追加：

```typescript
import { activateProject, archiveProject, blockProject, createProject } from "./pure.js"
import type { Project, ProjectId, WorkspaceRoot } from "./types.js"

describe("project lifecycle", () => {
  const id = "proj-1" as ProjectId
  const root = "/ws" as WorkspaceRoot

  it("creates a project with active state", () => {
    const p = createProject({ id, name: "Demo", workspaceRoot: root })
    expect(p.status).toBe("active")
    expect(p.createdAt).toBeGreaterThan(0)
  })
  it("blocks and unblocks a project", () => {
    let p = createProject({ id, name: "Demo", workspaceRoot: root })
    p = blockProject(p, "audit")
    expect(p.status).toBe("blocked")
    p = activateProject(p)
    expect(p.status).toBe("active")
  })
  it("archives a project", () => {
    let p = createProject({ id, name: "Demo", workspaceRoot: root })
    p = archiveProject(p)
    expect(p.status).toBe("archived")
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/projects/pure.test.ts 2>&1 | tail -20
```

Expected: 失败，引用 `activateProject` / `archiveProject` / `blockProject` 不存在。

- [ ] **Step 3: 扩展 types.ts 加 Project 状态枚举与函数签名]

```typescript
export type ProjectId = string & { readonly __brand: "ProjectId" }
export type WorkspaceRoot = string & { readonly __brand: "WorkspaceRoot" }
export type ProjectStatus = "active" | "blocked" | "archived"

export interface Project {
  readonly id: ProjectId
  readonly name: string
  readonly workspaceRoot: WorkspaceRoot
  readonly status: ProjectStatus
  readonly createdAt: number
  readonly blockedReason: string | null
}
```

- [ ] **Step 4: 扩展 pure.ts]

```typescript
import type { Project, ProjectId, ProjectStatus, WorkspaceRoot } from "./types.js"

export function createProject(input: {
  id: ProjectId
  name: string
  workspaceRoot: WorkspaceRoot
}): Project {
  return {
    id: input.id,
    name: input.name,
    workspaceRoot: input.workspaceRoot,
    status: "active" as ProjectStatus,
    createdAt: Date.now(),
    blockedReason: null,
  }
}

export function activateProject(p: Project): Project {
  return { ...p, status: "active" as ProjectStatus, blockedReason: null }
}

export function blockProject(p: Project, reason: string): Project {
  if (p.status === "archived") {
    throw new Error("cannot block archived project")
  }
  return { ...p, status: "blocked" as ProjectStatus, blockedReason: reason }
}

export function archiveProject(p: Project): Project {
  return { ...p, status: "archived" as ProjectStatus, blockedReason: null }
}
```

- [ ] **Step 5: 运行测试确认通过]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/projects/pure.test.ts 2>&1 | tail -10
```

Expected: PASS。

### Task 1.2: 扩展 Conversation 上下文

**Files:**
- Modify: `butler-v5/packages/domain/src/conversation/types.ts`
- Modify: `butler-v5/packages/domain/src/conversation/transitions.ts`
- Create: `butler-v5/packages/domain/src/conversation/events.ts`
- Modify: `butler-v5/packages/domain/src/conversation/index.ts`
- Modify: `butler-v5/packages/domain/src/conversation/transitions.test.ts`

- [ ] **Step 1: 写失败测试]

在 `transitions.test.ts` 末尾追加：

```typescript
import {
  applyToolResult,
  openTurn,
  submitUserMessage,
} from "./transitions.js"
import type { Conversation, Message, Turn } from "./types.js"

describe("conversation transitions", () => {
  const empty: Conversation = {
    id: "conv-1",
    projectId: "proj-1",
    status: "open",
    turns: [],
  }

  it("opens a turn on user message", () => {
    const c = submitUserMessage(empty, "hello")
    expect(c.turns.length).toBe(1)
    expect(c.turns[0]?.status).toBe("running")
  })

  it("applies a successful tool result", () => {
    const c0 = submitUserMessage(empty, "hi")
    const c1 = openTurn(c0, { toolCallId: "tc-1" })
    const c2 = applyToolResult(c1, { toolCallId: "tc-1", output: "ok" })
    expect(c2.turns[0]?.status).toBe("tooled")
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/conversation/transitions.test.ts 2>&1 | tail -15
```

Expected: 失败，引用 `submitUserMessage` / `applyToolResult` / `openTurn`。

- [ ] **Step 3: 扩展 types.ts 加 Turn 状态与 Message ADT]

```typescript
export type ConversationId = string & { readonly __brand: "ConversationId" }
export type ProjectIdRef = string & { readonly __brand: "ProjectIdRef" }
export type TurnId = string & { readonly __brand: "TurnId" }
export type ToolCallId = string & { readonly __brand: "ToolCallId" }

export type ConversationStatus = "open" | "running" | "waiting" | "completed"

export type TurnStatus = "running" | "responded" | "tooled" | "completed" | "failed"

export interface Message {
  readonly role: "user" | "assistant" | "system" | "tool"
  readonly content: string
}

export interface Turn {
  readonly id: TurnId
  readonly status: TurnStatus
  readonly userMessage: Message | null
  readonly assistantMessage: Message | null
  readonly toolCallId: ToolCallId | null
  readonly toolOutput: string | null
}

export interface Conversation {
  readonly id: ConversationId
  readonly projectId: ProjectIdRef
  readonly status: ConversationStatus
  readonly turns: ReadonlyArray<Turn>
}
```

- [ ] **Step 4: 实现 transitions.ts 新函数]

```typescript
import type { Conversation, Message, Turn, TurnId, ToolCallId } from "./types.js"

let turnSeq = 0
const newTurnId = (): TurnId => `turn-${++turnSeq}` as TurnId

export function submitUserMessage(c: Conversation, content: string): Conversation {
  if (c.status === "completed") {
    throw new Error("cannot append to completed conversation")
  }
  const turn: Turn = {
    id: newTurnId(),
    status: "running",
    userMessage: { role: "user", content },
    assistantMessage: null,
    toolCallId: null,
    toolOutput: null,
  }
  return { ...c, status: "running" as const, turns: [...c.turns, turn] }
}

export function openTurn(c: Conversation, _input: { toolCallId: ToolCallId }): Conversation {
  if (c.turns.length === 0) {
    throw new Error("no active turn")
  }
  const idx = c.turns.length - 1
  const cur = c.turns[idx]!
  const next: Turn = { ...cur, toolCallId: _input.toolCallId }
  const turns = c.turns.slice(0, idx).concat(next)
  return { ...c, turns }
}

export function applyToolResult(
  c: Conversation,
  input: { toolCallId: ToolCallId; output: string },
): Conversation {
  const idx = c.turns.findIndex((t) => t.toolCallId === input.toolCallId)
  if (idx < 0) {
    throw new Error("toolCallId not found")
  }
  const cur = c.turns[idx]!
  const next: Turn = { ...cur, toolOutput: input.output, status: "tooled" }
  const turns = c.turns.slice(0, idx).concat(next, c.turns.slice(idx + 1))
  return { ...c, turns }
}
```

- [ ] **Step 5: 更新 index.ts 导出]

```typescript
export * from "./types.js"
export * from "./transitions.js"
```

- [ ] **Step 6: 运行测试确认通过]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/conversation/transitions.test.ts 2>&1 | tail -10
```

Expected: PASS。

### Task 1.3: 端到端门禁验证

- [ ] **Step 1: 验证 R2.1 全包]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test 2>&1 | tail -8
echo "exit=$?"
bash /home/ailearn/projects/WFXM/butler-v5/scripts/typecheck-gate.sh
echo "gate_exit=$?"
```

Expected: test exit 0；gate exit 0。

### R2.1 退出条件

- Project lifecycle 状态机 3 个 transition 全部覆盖；
- Conversation 单轮状态机新增 submit/open/apply 三个 transition 全部覆盖；
- Domain 零 I/O 门禁仍绿；
- typecheck-gate 退出码 0。

---

## R2.2: Tools + Workflow + Memory

### Task 2.1: Tools 上下文补全

**Files:**
- Modify: `butler-v5/packages/domain/src/tools/types.ts`
- Modify: `butler-v5/packages/domain/src/tools/pure.ts`
- Modify: `butler-v5/packages/domain/src/tools/index.ts`
- Modify: `butler-v5/packages/domain/src/tools/pure.test.ts`

- [ ] **Step 1: 写失败测试]

在 `pure.test.ts` 末尾追加：

```typescript
import { describeCommandSpec, validateToolDefinition, type ToolDefinition, type CommandSpec } from "./pure.js"
import type { ToolName } from "./types.js"

describe("tools validation", () => {
  it("accepts a read_file definition", () => {
    const def: ToolDefinition = {
      name: "read_file" as ToolName,
      parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
      result: { type: "string" },
      risk: "low",
    }
    expect(validateToolDefinition(def)).toBe(true)
  })

  it("describes a command spec without shell metacharacters", () => {
    const spec: CommandSpec = {
      executable: "ls",
      args: ["-la"],
      cwd: "/ws",
      timeoutMs: 1000,
      network: "none",
    }
    const desc = describeCommandSpec(spec)
    expect(desc.executable).toBe("ls")
    expect(desc.args.join(" ")).toBe("-la")
    expect(desc.network).toBe("none")
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/tools/pure.test.ts 2>&1 | tail -15
```

Expected: 失败，引用 `ToolDefinition` / `CommandSpec` / `validateToolDefinition` / `describeCommandSpec`。

- [ ] **Step 3: 扩展 types.ts]

```typescript
export type ToolName = string & { readonly __brand: "ToolName" }
export type RiskLevel = "low" | "medium" | "high"

export interface CommandSpec {
  readonly executable: string
  readonly args: ReadonlyArray<string>
  readonly cwd: string
  readonly timeoutMs: number
  readonly network: "none" | "allowlist"
}

export interface ToolDefinition {
  readonly name: ToolName
  readonly parameters: Record<string, unknown>
  readonly result: Record<string, unknown>
  readonly risk: RiskLevel
}
```

- [ ] **Step 4: 实现 pure.ts]

```typescript
import type { CommandSpec, RiskLevel, ToolDefinition, ToolName } from "./types.js"

const FORBIDDEN_SHELL = /[;&|`$<>(){}\[\]\\\n]/

export function validateToolDefinition(def: ToolDefinition): boolean {
  if (def.name === "" || def.risk === "high") {
    return false
  }
  if (!def.parameters || !def.result) {
    return false
  }
  return true
}

export function describeCommandSpec(spec: CommandSpec): {
  executable: string
  args: ReadonlyArray<string>
  timeoutMs: number
  network: CommandSpec["network"]
} {
  if (FORBIDDEN_SHELL.test(spec.executable)) {
    throw new Error("executable contains shell metacharacter")
  }
  for (const a of spec.args) {
    if (FORBIDDEN_SHELL.test(a)) {
      throw new Error(`arg contains shell metacharacter: ${a}`)
    }
  }
  return {
    executable: spec.executable,
    args: spec.args,
    timeoutMs: spec.timeoutMs,
    network: spec.network,
  }
}
```

- [ ] **Step 5: 运行测试确认通过]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/tools/pure.test.ts 2>&1 | tail -10
```

Expected: PASS。

### Task 2.2: Workflow 状态机补全

**Files:**
- Modify: `butler-v5/packages/domain/src/workflows/types.ts`
- Modify: `butler-v5/packages/domain/src/workflows/transitions.ts`
- Modify: `butler-v5/packages/domain/src/workflows/index.ts`
- Modify: `butler-v5/packages/domain/src/workflows/transitions.test.ts`

- [ ] **Step 1: 写失败测试]

在 `transitions.test.ts` 末尾追加：

```typescript
import {
  advanceStep,
  failWorkflow,
  pendingWorkflow,
  startWorkflow,
  waitForApproval,
} from "./transitions.js"
import type { WorkflowRun, WorkflowStep } from "./types.js"

describe("workflow lifecycle", () => {
  const steps: WorkflowStep[] = [
    { id: "s1", kind: "tool", spec: { executable: "x", args: [], cwd: "/", timeoutMs: 1, network: "none" } },
    { id: "s2", kind: "approval", approver: "owner" },
  ]
  it("starts a workflow with steps", () => {
    const w = startWorkflow("wf-1", steps)
    expect(w.status).toBe("pending")
  })
  it("advances a step", () => {
    let w = startWorkflow("wf-1", steps)
    w = pendingWorkflow(w)
    w = advanceStep(w, "s1")
    expect(w.currentStepId).toBe("s2")
  })
  it("pauses for approval", () => {
    let w = startWorkflow("wf-1", steps)
    w = pendingWorkflow(w)
    w = waitForApproval(w, "s2", "owner")
    expect(w.status).toBe("waiting_approval")
  })
  it("fails the workflow", () => {
    let w = startWorkflow("wf-1", steps)
    w = failWorkflow(w, "boom")
    expect(w.status).toBe("failed")
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/workflows/transitions.test.ts 2>&1 | tail -15
```

Expected: 失败，引用 `WorkflowStep` / `WorkflowRun` / 4 个 transition 函数。

- [ ] **Step 3: 扩展 types.ts]

```typescript
import type { CommandSpec } from "../tools/types.js"

export type WorkflowId = string & { readonly __brand: "WorkflowId" }
export type WorkflowStepId = string & { readonly __brand: "WorkflowStepId" }

export type WorkflowStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"

export type WorkflowStep =
  | { readonly id: WorkflowStepId; readonly kind: "tool"; readonly spec: CommandSpec }
  | { readonly id: WorkflowStepId; readonly kind: "approval"; readonly approver: string }
  | { readonly id: WorkflowStepId; readonly kind: "delegate"; readonly role: string }

export interface WorkflowRun {
  readonly id: WorkflowId
  readonly status: WorkflowStatus
  readonly steps: ReadonlyArray<WorkflowStep>
  readonly currentStepId: WorkflowStepId | null
  readonly error: string | null
}
```

- [ ] **Step 4: 实现 transitions.ts]

```typescript
import type {
  WorkflowId,
  WorkflowRun,
  WorkflowStep,
  WorkflowStepId,
} from "./types.js"

export function startWorkflow(id: WorkflowId, steps: ReadonlyArray<WorkflowStep>): WorkflowRun {
  if (steps.length === 0) {
    throw new Error("workflow requires at least one step")
  }
  return {
    id,
    status: "pending",
    steps,
    currentStepId: null,
    error: null,
  }
}

export function pendingWorkflow(w: WorkflowRun): WorkflowRun {
  return { ...w, status: "running" }
}

export function advanceStep(w: WorkflowRun, stepId: WorkflowStepId): WorkflowRun {
  const idx = w.steps.findIndex((s) => s.id === stepId)
  if (idx < 0) {
    throw new Error("step not found")
  }
  if (idx + 1 >= w.steps.length) {
    return { ...w, status: "completed", currentStepId: null }
  }
  const next = w.steps[idx + 1]!
  return { ...w, currentStepId: next.id, status: "running" }
}

export function waitForApproval(
  w: WorkflowRun,
  stepId: WorkflowStepId,
  _approver: string,
): WorkflowRun {
  if (!w.steps.find((s) => s.id === stepId)) {
    throw new Error("step not found")
  }
  return { ...w, status: "waiting_approval", currentStepId: stepId }
}

export function failWorkflow(w: WorkflowRun, error: string): WorkflowRun {
  return { ...w, status: "failed", error }
}
```

- [ ] **Step 5: index.ts 导出]

```typescript
export * from "./types.js"
export * from "./transitions.js"
```

- [ ] **Step 6: 运行测试确认通过]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/workflows/transitions.test.ts 2>&1 | tail -10
```

Expected: PASS。

### Task 2.3: Memory 召回策略

**Files:**
- Modify: `butler-v5/packages/domain/src/memory/types.ts`
- Modify: `butler-v5/packages/domain/src/memory/pure.ts`
- Modify: `butler-v5/packages/domain/src/memory/index.ts`
- Modify: `butler-v5/packages/domain/src/memory/pure.test.ts`

- [ ] **Step 1: 写失败测试]

在 `pure.test.ts` 末尾追加：

```typescript
import {
  decayScore,
  fuseResults,
  rankByRecency,
  type MemoryRecord,
  type RecallResult,
} from "./pure.js"

describe("memory recall", () => {
  const now = 1_000_000
  const records: MemoryRecord[] = [
    { id: "a", text: "alpha", createdAt: now - 100, lastAccessAt: now - 50, weight: 0.9 },
    { id: "b", text: "beta", createdAt: now - 1000, lastAccessAt: now - 1, weight: 0.5 },
  ]
  it("ranks by recency", () => {
    const ranked = rankByRecency(records, now)
    expect(ranked[0]?.id).toBe("b")
  })
  it("fuses two result sets with dedup", () => {
    const r1: RecallResult[] = [{ record: records[0]!, score: 0.9 }]
    const r2: RecallResult[] = [{ record: records[0]!, score: 0.7 }, { record: records[1]!, score: 0.5 }]
    const merged = fuseResults(r1, r2)
    expect(merged.length).toBe(2)
    expect(merged.find((r) => r.record.id === "a")?.score).toBeCloseTo(0.9)
  })
  it("decays an old access", () => {
    const r = decayScore(records[0]!, now)
    expect(r).toBeGreaterThan(0)
    expect(r).toBeLessThan(records[0]!.weight)
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/memory/pure.test.ts 2>&1 | tail -15
```

Expected: 失败。

- [ ] **Step 3: 扩展 types.ts]

```typescript
export type MemoryId = string & { readonly __brand: "MemoryId" }

export interface MemoryRecord {
  readonly id: MemoryId
  readonly text: string
  readonly createdAt: number
  readonly lastAccessAt: number
  readonly weight: number
}

export interface RecallResult {
  readonly record: MemoryRecord
  readonly score: number
}
```

- [ ] **Step 4: 实现 pure.ts]

```typescript
import type { MemoryRecord, RecallResult } from "./types.js"

const HALF_LIFE_MS = 30 * 24 * 60 * 60 * 1000 // 30 days

export function decayScore(record: MemoryRecord, now: number): number {
  const age = Math.max(0, now - record.lastAccessAt)
  const factor = Math.pow(0.5, age / HALF_LIFE_MS)
  return record.weight * factor
}

export function rankByRecency(
  records: ReadonlyArray<MemoryRecord>,
  now: number,
): ReadonlyArray<MemoryRecord> {
  return [...records].sort((a, b) => decayScore(b, now) - decayScore(a, now))
}

export function fuseResults(
  a: ReadonlyArray<RecallResult>,
  b: ReadonlyArray<RecallResult>,
): ReadonlyArray<RecallResult> {
  const map = new Map<string, RecallResult>()
  for (const r of [...a, ...b]) {
    const existing = map.get(r.record.id)
    if (!existing || r.score > existing.score) {
      map.set(r.record.id, r)
    }
  }
  return Array.from(map.values())
}
```

- [ ] **Step 5: 运行测试确认通过]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/memory/pure.test.ts 2>&1 | tail -10
```

Expected: PASS。

### R2.2 退出条件

- Tools / Workflow / Memory 三大上下文 9 个新增纯函数 + 3 个 ADT 全部覆盖测试；
- Domain 零 I/O 门禁仍绿；
- typecheck-gate 退出码 0。

---

## R2.3: Events + ADT 治理

### Task 3.1: 补 ApprovalRequest ADT 与 decidePermission 纯函数

**Files:**
- Modify: `butler-v5/packages/domain/src/permissions/types.ts`
- Create: `butler-v5/packages/domain/src/permissions/pure.ts`
- Modify: `butler-v5/packages/domain/src/permissions/index.ts`
- Create: `butler-v5/packages/domain/src/permissions/pure.test.ts`

- [ ] **Step 1: 写失败测试]

`butler-v5/packages/domain/src/permissions/pure.test.ts`：

```typescript
import { describe, expect, it } from "vitest"
import { decidePermission } from "./pure.js"
import type { ApprovalRequest, Capability, PermissionPolicy } from "./types.js"

describe("decidePermission", () => {
  const basePolicy: PermissionPolicy = {
    allowed: [{ tool: "read_file", paths: ["*"] }],
    denied: [],
    requireApproval: [{ tool: "terminal", approver: "owner" }],
  }
  const request: ApprovalRequest = {
    tool: "read_file",
    resource: { path: "/ws/file.txt" },
  }
  it("allows whitelisted tool", () => {
    const d = decidePermission(request, basePolicy)
    expect(d._tag).toBe("Allow")
  })
  it("denies blacklisted tool", () => {
    const req: ApprovalRequest = { tool: "shell", resource: { path: "/" } }
    expect(decidePermission(req, basePolicy)._tag).toBe("Deny")
  })
  it("requires approval for sensitive tool", () => {
    const req: ApprovalRequest = { tool: "terminal", resource: { path: "/" } }
    expect(decidePermission(req, basePolicy)._tag).toBe("RequireApproval")
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/permissions/pure.test.ts 2>&1 | tail -10
```

Expected: 失败。

- [ ] **Step 3: 扩展 types.ts]

```typescript
export type ToolNameRef = string & { readonly __brand: "ToolNameRef" }
export type PathPattern = string

export interface ApprovalRequest {
  readonly tool: ToolNameRef
  readonly resource: { readonly path: string }
  readonly action: "read" | "write" | "execute" | "delegate"
}

export interface PermissionPolicy {
  readonly allowed: ReadonlyArray<{ tool: ToolNameRef; paths: ReadonlyArray<PathPattern> }>
  readonly denied: ReadonlyArray<{ tool: ToolNameRef; reason: string }>
  readonly requireApproval: ReadonlyArray<{ tool: ToolNameRef; approver: string }>
}

export type PolicyDecision =
  | { readonly _tag: "Allow"; readonly capability: Capability }
  | { readonly _tag: "Deny"; readonly reason: string }
  | { readonly _tag: "RequireApproval"; readonly approver: string }

export interface Capability {
  readonly tool: ToolNameRef
  readonly expiresAt: number
}
```

- [ ] **Step 4: 实现 pure.ts]

```typescript
import type {
  ApprovalRequest,
  Capability,
  PermissionPolicy,
  PolicyDecision,
  ToolNameRef,
} from "./types.js"

const matchesPath = (pattern: string, path: string): boolean => {
  if (pattern === "*") return true
  if (pattern.endsWith("*")) return path.startsWith(pattern.slice(0, -1))
  return pattern === path
}

const matchRule = (
  rule: { tool: ToolNameRef; paths?: ReadonlyArray<string> },
  tool: ToolNameRef,
  path: string,
): boolean => {
  if (rule.tool !== tool) return false
  if (!rule.paths || rule.paths.length === 0) return true
  return rule.paths.some((p) => matchesPath(p, path))
}

export function decidePermission(
  request: ApprovalRequest,
  policy: PermissionPolicy,
): PolicyDecision {
  for (const rule of policy.denied) {
    if (rule.tool === request.tool) {
      return { _tag: "Deny", reason: rule.reason }
    }
  }
  for (const rule of policy.requireApproval) {
    if (rule.tool === request.tool) {
      return { _tag: "RequireApproval", approver: rule.approver }
    }
  }
  for (const rule of policy.allowed) {
    if (matchRule(rule, request.tool, request.resource.path)) {
      const capability: Capability = {
        tool: request.tool,
        expiresAt: Date.now() + 5 * 60 * 1000,
      }
      return { _tag: "Allow", capability }
    }
  }
  return { _tag: "Deny", reason: "no matching allow rule" }
}
```

- [ ] **Step 5: index.ts 导出]

```typescript
export * from "./types.js"
export * from "./pure.js"
```

- [ ] **Step 6: 运行测试]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/permissions/pure.test.ts 2>&1 | tail -10
```

Expected: PASS。

### Task 3.2: 扩展 Event Envelope 与 EventRegistry

**Files:**
- Modify: `butler-v5/packages/domain/src/event-sourcing.ts`
- Modify: `butler-v5/packages/domain/src/event-sourcing.test.ts`
- Modify: `butler-v5/packages/domain/src/index.ts`

- [ ] **Step 1: 写失败测试]

在 `event-sourcing.test.ts` 末尾追加：

```typescript
import { buildEnvelope, validateEnvelope, type DomainEvent, type StreamType } from "./event-sourcing.js"

describe("event envelope", () => {
  const ev: DomainEvent = { _tag: "ConversationStarted" } as DomainEvent
  it("builds a valid envelope", () => {
    const env = buildEnvelope({
      streamId: "s-1",
      streamType: "conversation" as StreamType,
      event: ev,
    })
    expect(env.streamId).toBe("s-1")
    expect(env.eventVersion).toBe(1)
    expect(validateEnvelope(env).ok).toBe(true)
  })
  it("rejects unknown envelope version", () => {
    const env = buildEnvelope({
      streamId: "s-1",
      streamType: "conversation" as StreamType,
      event: ev,
    })
    const broken = { ...env, eventVersion: 99 }
    expect(validateEnvelope(broken).ok).toBe(false)
  })
})
```

- [ ] **Step 2: 运行确认失败]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/event-sourcing.test.ts 2>&1 | tail -10
```

Expected: 失败。

- [ ] **Step 3: 扩展 event-sourcing.ts]

在文件末尾追加：

```typescript
export type StreamType = "conversation" | "project" | "workflow" | "approval" | "memory"
export type ActorRef = { readonly kind: "owner" | "agent" | "system"; readonly id: string }

export interface EventEnvelope {
  readonly eventId: string
  readonly eventType: string
  readonly eventVersion: number
  readonly streamId: string
  readonly streamType: StreamType
  readonly streamVersion: number
  readonly occurredAt: string
  readonly causationId: string | null
  readonly correlationId: string
  readonly actor: ActorRef
  readonly payload: unknown
}

let seq = 0
export function buildEnvelope(input: {
  streamId: string
  streamType: StreamType
  event: DomainEvent
}): EventEnvelope {
  seq += 1
  const eventId = `evt-${Date.now()}-${seq}`
  return {
    eventId,
    eventType: (input.event as { _tag: string })._tag,
    eventVersion: 1,
    streamId: input.streamId,
    streamType: input.streamType,
    streamVersion: 1,
    occurredAt: new Date().toISOString(),
    causationId: null,
    correlationId: `corr-${Date.now()}`,
    actor: { kind: "system", id: "domain" },
    payload: input.event,
  }
}

export function validateEnvelope(env: EventEnvelope): { ok: boolean; reason?: string } {
  if (env.eventVersion !== 1) {
    return { ok: false, reason: `unsupported eventVersion ${env.eventVersion}` }
  }
  if (env.streamVersion < 1) {
    return { ok: false, reason: "streamVersion must be >= 1" }
  }
  if (!env.correlationId) {
    return { ok: false, reason: "correlationId required" }
  }
  return { ok: true }
}
```

- [ ] **Step 4: 运行测试]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test packages/domain/src/event-sourcing.test.ts 2>&1 | tail -10
```

Expected: PASS。

### R2.3 退出条件

- ApprovalRequest / PermissionPolicy / decidePermission ADT 落地；
- Event Envelope 与 validateEnvelope 纯函数落地；
- Domain 零 I/O 门禁仍绿；
- typecheck-gate 退出码 0。

---

## R2.4: Contracts Schema

### Task 4.1: API/Event/Plugin Manifest Contract Schema

**Files:**
- Create: `butler-v5/packages/contracts/src/api.ts`
- Create: `butler-v5/packages/contracts/src/events.ts`
- Create: `butler-v5/packages/contracts/src/plugin.ts`
- Create: `butler-v5/packages/contracts/src/index.ts`
- Create: `butler-v5/packages/contracts/tsconfig.json`
- Create: `butler-v5/packages/contracts/package.json`
- Create: `butler-v5/packages/contracts/src/contracts.test.ts`
- Modify: `butler-v5/pnpm-workspace.yaml`
- Modify: `butler-v5/tsconfig.json`
- Modify: `butler-v5/.eslintrc.json`
- Modify: `butler-v5/tests/architecture/dependency-direction.test.ts`

- [ ] **Step 1: 创建 packages/contracts 子包目录]

修改 `butler-v5/pnpm-workspace.yaml`：

```yaml
packages:
  - "packages/*"
  - "apps/*"
  - "packages/contracts"
```

实际上 `packages/*` 已匹配新目录；无需修改。

- [ ] **Step 2: 创建 packages/contracts/package.json]

```json
{
  "name": "@butler/contracts",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  },
  "types": "./src/index.ts",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  }
}
```

- [ ] **Step 3: 创建 packages/contracts/tsconfig.json]

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 4: 创建 packages/contracts/src/api.ts]

```typescript
import type { ToolName } from "../domain/src/tools/types.js"

export type ApiVersion = "v1"

export interface StartConversationRequest {
  readonly apiVersion: ApiVersion
  readonly projectId: string
  readonly toolName: ToolName | null
  readonly content: string
}

export interface StartConversationResponse {
  readonly conversationId: string
  readonly turnId: string
}

export type ApiResult<T> = { readonly ok: true; readonly value: T } | { readonly ok: false; readonly code: string; readonly message: string }
```

- [ ] **Step 5: 创建 packages/contracts/src/events.ts]

```typescript
import type { EventEnvelope, StreamType } from "../domain/src/event-sourcing.js"

export type ContractEvent = EventEnvelope & { readonly streamType: StreamType }

export interface EventSubscribeRequest {
  readonly streamTypes: ReadonlyArray<StreamType>
  readonly fromVersion: number
}

export interface EventBatchResponse {
  readonly events: ReadonlyArray<ContractEvent>
  readonly nextVersion: number
}
```

- [ ] **Step 6: 创建 packages/contracts/src/plugin.ts]

```typescript
import type { ToolName } from "../domain/src/tools/types.js"

export type PluginTrust = "bundled" | "github" | "url" | "clawhub" | "marketplace" | "lobehub"

export interface PluginManifest {
  readonly name: string
  readonly version: string
  readonly trust: PluginTrust
  readonly provides: ReadonlyArray<"tool" | "channel" | "guard" | "event-source">
  readonly tools: ReadonlyArray<{ readonly name: ToolName; readonly risk: "low" | "medium" | "high" }>
  readonly requiredCapabilities: ReadonlyArray<"fs.read" | "fs.write" | "net" | "subprocess" | "memory.write" | "long-running">
  readonly signature: string
}
```

- [ ] **Step 7: 创建 packages/contracts/src/index.ts]

```typescript
export * from "./api.js"
export * from "./events.js"
export * from "./plugin.js"
```

- [ ] **Step 8: 写契约测试]

`butler-v5/packages/contracts/src/contracts.test.ts`：

```typescript
import { describe, expect, it } from "vitest"
import type { PluginManifest } from "./plugin.js"
import type { StartConversationRequest, StartConversationResponse } from "./api.js"
import type { EventBatchResponse, EventSubscribeRequest } from "./events.js"

describe("contracts shape", () => {
  it("StartConversationRequest/Response compile", () => {
    const req: StartConversationRequest = {
      apiVersion: "v1",
      projectId: "p1",
      toolName: null,
      content: "hi",
    }
    const res: StartConversationResponse = { conversationId: "c1", turnId: "t1" }
    expect(req.apiVersion).toBe("v1")
    expect(res.turnId).toBe("t1")
  })
  it("PluginManifest enforces trust enum", () => {
    const m: PluginManifest = {
      name: "demo",
      version: "0.0.1",
      trust: "bundled",
      provides: ["tool"],
      tools: [],
      requiredCapabilities: [],
      signature: "ok",
    }
    expect(m.trust).toBe("bundled")
  })
  it("EventSubscribeRequest/Response compile", () => {
    const r: EventSubscribeRequest = { streamTypes: ["conversation"], fromVersion: 1 }
    const b: EventBatchResponse = { events: [], nextVersion: 1 }
    expect(b.nextVersion).toBe(1)
    expect(r.streamTypes).toContain("conversation")
  })
})
```

- [ ] **Step 9: 更新根 tsconfig.json include 以包含 contracts 包]

修改 `butler-v5/tsconfig.json`：

```json
"include": ["packages/*/src/**/*.ts", "apps/*/src/**/*.ts"]
```

`packages/*` 仍匹配 `packages/contracts/src`；无需修改。

- [ ] **Step 10: 更新 .eslintrc.json parserOptions.project]

修改 `butler-v5/.eslintrc.json` 的 `parserOptions.project` 数组，追加 `"./packages/contracts/tsconfig.json"`。

- [ ] **Step 11: 更新 dependency-direction 测试]

修改 `butler-v5/tests/architecture/dependency-direction.test.ts`：

```typescript
it("contracts may import domain only", () => {
  const files = listTs(join(process.cwd(), "packages/contracts/src"))
  for (const file of files) {
    const src = readFileSync(file, "utf8")
    expect(findPkgImports(src, "application")).toEqual([])
    expect(findPkgImports(src, "infrastructure")).toEqual([])
    expect(findPkgImports(src, "ports")).toEqual([])
  }
})
```

- [ ] **Step 12: 运行所有门禁]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 typecheck 2>&1 | tail -5
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test 2>&1 | tail -8
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 lint 2>&1 | tail -5
bash /home/ailearn/projects/WFXM/butler-v5/scripts/typecheck-gate.sh
```

Expected: 全部 exit 0。

### R2.4 退出条件

- `packages/contracts` 新子包加入 typecheck / lint / test；
- API / Event / Plugin Manifest Schema 全部通过 typecheck + 测试；
- domain-zero-io 与 dependency-direction 门禁仍绿；
- typecheck-gate 退出码 0。

---

## R2.5: 端到端门禁

### Task 5.1: 合并所有 R2 门禁

**Files:**
- Create: `butler-v5/tests/architecture/r2-end-to-end.test.ts`

- [ ] **Step 1: 写跨子项目门禁测试]

```typescript
import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("R2 end-to-end gates", () => {
  it("full test suite passes", () => {
    const out = execFileSync("pnpm", ["test", "--reporter=dot"], {
      cwd: process.cwd(),
      encoding: "utf8",
    })
    expect(out).toContain("Test Files")
  })
  it("typecheck passes", () => {
    execFileSync("pnpm", ["typecheck"], { cwd: process.cwd(), encoding: "utf8" })
  })
  it("lint passes", () => {
    execFileSync("pnpm", ["lint"], { cwd: process.cwd(), encoding: "utf8" })
  })
  it("format passes", () => {
    execFileSync("pnpm", ["format:check"], { cwd: process.cwd(), encoding: "utf8" })
  })
})
```

- [ ] **Step 2: 运行]

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test tests/architecture/r2-end-to-end.test.ts 2>&1 | tail -10
```

Expected: 4/4 PASS。

### Task 5.2: 收口报告

**Files:**
- Create: `/home/ailearn/projects/WFXM/.blackboard/shifts/2026-08-08-claude-code-004.md`

- [ ] **Step 1: 写 R2 收口 shift 卡]

frontmatter 与 shift 001–003 同形态（schema_version: 1, agent: claude-code, `intent: 记录 R2 Domain + Contracts 收口`），正文覆盖：

- R2.0–R2.5 全部 6 个子项目完成与残留偏差；
- 新增领域纯函数与 ADT 清单；
- typecheck / lint / format / test 全部退出码 0；
- 已知妥协（lint typed rules 在 R2 范围内闭环；R1 偏差已全部消化）；
- 下一阶段建议（R3 Persistence Kernel）。

- [ ] **Step 2: 验证 schema]

```bash
python3 -c "import yaml; print(yaml.safe_load(open('/home/ailearn/projects/WFXM/.blackboard/shifts/2026-08-08-claude-code-004.md').read(8))" | head -5
```

Expected: `shift_id: 2026-08-08-claude-code-004`，`schema_version: 1`。

### R2.5 退出条件

- typecheck / lint / format / test / typecheck-gate 全部退出码 0；
- R1 残留 prettier / lint 偏差全部消化；
- R2 收口 shift 卡已落盘。

---

## 总体 R2 退出条件

- R1 全部偏差（prettier / lint typed-rules）已消化；
- 新增 Project / Conversation / Tools / Workflow / Memory / Permissions 纯函数与 ADT；
- Event Envelope 与 validateEnvelope 落地；
- `packages/contracts` 子包加入 typecheck / lint / test；
- typecheck-gate 退出码 0；
- 黑板 shift 卡 2026-08-08-claude-code-004 已落盘。

---

## 与规格覆盖检查

- 规格 §5.1 上下文：R2.1 / R2.2 覆盖
- 规格 §5.2 聚合：R2.1 / R2.2 覆盖
- 规格 §5.3 UseCase：R2 仅交付纯函数，UseCase 在 R3 Persistence Kernel 后续
- 规格 §6.1 模型输出边界：R2.3 ApprovalRequest/PolicyDecision 覆盖
- 规格 §6.2 AgentKernel：Runtime 阶段（R4）
- 规格 §7.1 三类事件：R2.3 Event Envelope 覆盖
- 规格 §7.2 Envelope 约束：R2.3 实现
- 规格 §8.2 纯 Policy Engine：R2.3 decidePermission 覆盖
- 规格 §12.1 迁移资产：R6 范围
- 规格 §13 阶段顺序：R2 → R3 → R4 → R5 → R6 → R7 全部覆盖
- 规格 §14 完成定义：R2 后 R3 启动时由子项目逐一收口
