# WFXM v5 全面替代 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Butler v5 TypeScript/Effect-TS 原型建设为能够替代 Butler v4 的单机自托管产品，并迁移 v4 核心资产。

**Architecture:** 采用强边界模块化单体：纯 `domain` 通过 `ports` 暴露副作用契约，`application` 负责用例和事务，`runtime` 负责 AgentKernel、Worker 与监督，`adapters` 负责 PostgreSQL、LLM、微信、文件、MCP 和观测。PostgreSQL Event Store 是事实源，Projection/Outbox 派生读模型和副作用；迁移使用 Strangler + Shadow + Cutover。

**Tech Stack:** TypeScript strict、Node.js 20、pnpm 9、Turborepo、Effect-TS 3、Drizzle、PostgreSQL 16 + pgvector、Vitest、ESLint、Prettier、ts-prune、Docker Compose、OpenTelemetry。

---

## 执行规则与当前基线

- 本规格覆盖 R0–R7 八个独立子项目。R0/R1 在本计划内细化到可直接执行；R2–R7 在进入阶段前从本文件拆成独立子计划。
- 根目录 `main` 当前有大量既有 modified/untracked v4 WIP；不得自动 stage、覆盖或混入 v5 提交。
- `butler-v5/` 当前未被 Git 跟踪；`pnpm typecheck` 通过，`pnpm lint` 因 `parserOptions.project` 失败，Vitest 因 pnpm workspace 链接重复收集测试。
- `packages/infrastructure/src/migration/v4-to-v5.ts` 和 `persistence/eventstore-live.ts` 是占位实现，不能作为阶段完成证据。
- `.butler/scope-boundaries.json` 中的 off-limits 文件只能由 Owner manual override 修改。
- 本计划中的 commit 步骤只在用户明确授权提交后执行；当前只生成计划，不写生产代码。

```text
R0 仓库/决策收口
  → R1 工程基线
  → R2 Domain + Contracts
  → R3 Persistence Kernel
  → R4 Agent Runtime
  → R5 Adapters + Delivery
  → R6 Migration + Shadow
  → R7 Cutover + Retirement
```

每个阶段都按以下循环推进：

```text
读取目标文件
  → 写失败测试或门禁
  → 运行并确认失败
  → 最小实现
  → 重跑测试
  → 提交（仅在用户授权后）
```

---

## R0：仓库与决策收口

### Task 1: 冻结当前工作区与 WIP 分类

**Files:**
- Create: `docs/analysis/wfxm-wip-inventory-2026-08-08.md`
- Reference: `docs/analysis/project-status-2026-08-08.md`
- Reference: `docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md`

- [ ] **Step 1: 采集不可变基线**

Run:

```bash
git -C /home/ailearn/projects/WFXM status --short
git -C /home/ailearn/projects/WFXM diff --stat
git -C /home/ailearn/projects/WFXM ls-files .wfxm_data
git -C /home/ailearn/projects/WFXM ls-files butler-v5
```

Expected: v4 modified/untracked 列表与状态报告一致；`butler-v5` 没有任何已跟踪文件。

- [ ] **Step 2: 生成 WIP 分类文档**

创建 `docs/analysis/wfxm-wip-inventory-2026-08-08.md`，内容至少包括：

```markdown
# WFXM 当前 WIP 分类（2026-08-08 冻结）

## 已跟踪并修改（M）
按 v4 主题分组，列出每个文件及其接入层级与 R0 之后的处理：
- 保留：必须随 v4 P0 修复 / 数据迁移携带
- 推 v4 main：已成熟可合并
- 转 v5：抽象适合 v5 体系
- 删除/暂缓：与目标不一致

## 未跟踪（??）
同上分类，单独标注 v5 原型目录。

## 拒绝写入的提交
明确：R0 结束前不得把 .wfxm_data 运行数据、butler-v5 原型、v4 WIP 合并。
```

- [ ] **Step 3: 决定手动提交边界**

仅当用户明确授权后，才把生成的文档与既有 blackboard shift 卡合并到一次手动 commit。不要使用自动 stage。

```bash
git -C /home/ailearn/projects/WFXM add docs/analysis/wfxm-wip-inventory-2026-08-08.md .blackboard/shifts/2026-08-08-claude-code-001.md
git -C /home/ailearn/projects/WFXM status --short
```

Expected: 只显示本步骤新加的文件。

### Task 2: 写入 v4/v5 终局 ADR

**Files:**
- Create: `docs/adr/2026-08-08-v4-to-v5-supersession.md`

- [ ] **Step 1: 起草 ADR 标题块**

```markdown
# ADR-0001: Butler v4 → v5 全面替代

- Status: Accepted
- Date: 2026-08-08
- Deciders: 项目 Owner
- Supersedes: v4 maintenance 计划、`butler-v5/` 原型声明

## Context
[引用 `project-status-2026-08-08.md` 与 `2026-08-08-wfxm-rearchitecture-design.md`，说明 v4 与 v5 并行的成本、风险和已有原型的能力。]

## Decision
- Butler v5 是唯一活动产品主线。
- Butler v4 进入 maintenance：仅接受 P0 安全/生产修复。
- 允许破坏性升级；不复刻 v4 命令、配置、API 表面。
- 部署目标为单机自托管 + Docker Compose。
- v5 数据迁移范围为项目、记忆、任务、审批、Skill 元数据、经验；旧会话与派生索引离线归档或重建。

## Consequences
[列出 v4 弃用、v5 平台、新 v4 维护责任、回滚窗口等。]

## Migration Plan Reference
- R0–R7 阶段定义见 `docs/superpowers/specs/2026-08-08-wfxm-rearchitecture-design.md`。
- 实施计划见 `docs/superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md`。
```

- [ ] **Step 2: Owner 复核与签发**

Owner 复核 ADR 文本，必要时在 PR 评论中追加修正。任何对 ADR 的改动都需 commit message 中带 `[MANUAL-OVERRIDE]`。

- [ ] **Step 3: 在 README 顶部添加 1 句话状态**

修改 `README.md` 顶部，使第一行包含：

```markdown
> 当前状态：Butler v4 maintenance，Butler v5 为唯一活动主线（ADR-0001）。
```

### Task 3: 隔离运行数据与配置

**Files:**
- Modify: `.gitignore` (根目录)
- Modify: `butler-v5/.gitignore`

- [ ] **Step 1: 把 .wfxm_data 加入根 .gitignore**

在 `.gitignore` 末尾追加：

```text
# runtime data
.wfxm_data/
```

验证:

```bash
git -C /home/ailearn/projects/WFXM check-ignore -v .wfxm_data/chromadb/chroma.sqlite3
```

Expected: 命中 ignore 规则。

- [ ] **Step 2: 同步 v5 gitignore**

在 `butler-v5/.gitignore` 末尾追加：

```text
# runtime
pgdata/
.scratch/
```

- [ ] **Step 3: 修复 worktree Hook 根路径解析**

`.claude/settings.json` 已被列入 off-limits，必须由 Owner manual override。把相对路径 `python3 scripts/ai_guard/...` 改为基于稳定项目根的解析，例如：

```json
"command": "python3 $CLAUDE_PROJECT_DIR/scripts/ai_guard/pre_tool_use_hook.py"
```

Owner 运行以下验证：

```bash
python3 $CLAUDE_PROJECT_DIR/scripts/ai_guard/pre_tool_use_hook.py --help
```

Expected: hook 脚本能被解析并以项目根为基准。

- [ ] **Step 4: 提交 ADR 与 ignore 调整（人工）**

```bash
git -C /home/ailearn/projects/WFXM status --short
```

仅在用户授权且 ADR 已签发后才执行提交：

```bash
git -C /home/ailearn/projects/WFXM add docs/adr/2026-08-08-v4-to-v5-supersession.md README.md .gitignore
git -C /home/ailearn/projects/WFXM commit -m "chore(r0): adopt ADR-0001, isolate runtime data, fix hook paths"
```

### R0 退出条件

- ADR-0001 已落盘并被 README 引用。
- `.wfxm_data/` 已被 gitignore。
- worktree Hook 根路径验证通过。
- 当前工作区 M 列表已被人工分类为“保留 / 推 v4 main / 转 v5 / 删除”。

---

## R1：v5 工程基线与可信门禁

### Task 4: 修复 Vitest 重复收集

**Files:**
- Modify: `butler-v5/vitest.config.ts`
- Create: `butler-v5/scripts/list-test-files.sh`
- Create: `butler-v5/tests/_meta/list-unique-test-files.test.ts`

- [ ] **Step 1: 写出唯一测试发现测试**

`butler-v5/tests/_meta/list-unique-test-files.test.ts`：

```typescript
import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"

describe("test discovery", () => {
  it("reports unique test source files", () => {
    const out = execFileSync("bash", ["scripts/list-test-files.sh"], {
      cwd: process.cwd(),
      encoding: "utf8",
    })
    const files = out.trim().split("\n").filter(Boolean)
    const unique = new Set(files)
    expect(files.length).toBe(unique.size)
    expect(files.length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: 写唯一测试清单脚本**

`butler-v5/scripts/list-test-files.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Only real source test files in packages/ apps/ tests/ ; skip node_modules and tsbuildinfo dirs.
find packages apps tests \
  \( -name node_modules -o -name .turbo -o -name dist \) -prune -o \
  -type f -name "*.test.ts" -print \
  | sort -u
```

```bash
chmod +x butler-v5/scripts/list-test-files.sh
```

Run:

```bash
bash /home/ailearn/projects/WFXM/butler-v5/scripts/list-test-files.sh | wc -l
```

Expected: 30–40 行（实际唯一测试源数量）。

- [ ] **Step 3: 修复 vitest 排除**

修改 `butler-v5/vitest.config.ts` 中的 `exclude`：

```typescript
exclude: [
  "**/node_modules/**",
  "**/dist/**",
  "**/.turbo/**",
  "**/*.tsbuildinfo",
],
```

`include` 保留为当前 `packages/**/*.test.ts` `apps/**/*.test.ts` `tests/**/*.test.ts`，但要求每个文件路径不能含 `node_modules` 段。

- [ ] **Step 4: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test
```

Expected: 测试文件数量与脚本一致（不再有 338 重复收集）。

### Task 5: 修复 ESLint typed rules

**Files:**
- Modify: `butler-v5/.eslintrc.json`
- Create: `butler-v5/eslint.config.mjs`
- Modify: `butler-v5/package.json`（scripts）

- [ ] **Step 1: 添加 `parserOptions.project`**

替换 `butler-v5/.eslintrc.json` 为：

```json
{
  "root": true,
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2022,
    "sourceType": "module",
    "project": [
      "./packages/*/tsconfig.json",
      "./apps/*/tsconfig.json",
      "./tests/**/tsconfig.json"
    ],
    "tsconfigRootDir": "."
  },
  "plugins": ["@typescript-eslint"],
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended"
  ],
  "rules": {
    "no-console": "warn",
    "no-debugger": "error",
    "no-eval": "error",
    "no-implied-eval": "error",
    "no-new-func": "error",
    "no-throw-literal": "error",
    "@typescript-eslint/no-unused-vars": ["warn", { "argsIgnorePattern": "^_", "varsIgnorePattern": "^_" }],
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-non-null-assertion": "warn",
    "@typescript-eslint/consistent-type-imports": ["warn", { "prefer": "type-imports", "fixStyle": "separate-type-imports" }],
    "@typescript-eslint/consistent-type-exports": "warn",
    "@typescript-eslint/array-type": ["warn", { "default": "array" }],
    "@typescript-eslint/prefer-readonly": "warn"
  },
  "ignorePatterns": ["dist/", "node_modules/", "coverage/", "*.tsbuildinfo", "hooks/"]
}
```

- [ ] **Step 2: 修复 lint 脚本**

修改 `butler-v5/package.json` 中 `lint` 脚本为：

```json
"lint": "eslint packages/ apps/ tests/ --ext .ts --max-warnings 0",
"lint:fix": "eslint packages/ apps/ tests/ --ext .ts --fix"
```

- [ ] **Step 3: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 lint
```

Expected: 退出码 0，或仅有受控 warning。

### Task 6: 调整 TypeScript 工程基线

**Files:**
- Modify: `butler-v5/tsconfig.base.json`
- Modify: `butler-v5/tsconfig.json`

- [ ] **Step 1: 收紧 base 配置**

修改 `butler-v5/tsconfig.base.json` 为：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noFallthroughCasesInSwitch": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

- [ ] **Step 2: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 typecheck
```

Expected: 0 错误。若有错误，按 `packages/.../tsconfig.json` 中 `extends` 链逐包修复。

### Task 7: 写死代码门禁

**Files:**
- Modify: `butler-v5/scripts/typecheck-gate.sh`

- [ ] **Step 1: 加入死代码与目录检查**

在 `butler-v5/scripts/typecheck-gate.sh` 的 `=== All gates passed ===` 之前追加：

```bash
echo "--- Running deadcode gate ---"
if pnpm deadcode 2>&1 | grep -E "used in module" ; then
  echo "deadcode: FAIL"
  exit 1
fi
echo "deadcode: PASS"
```

- [ ] **Step 2: 验证**

```bash
bash /home/ailearn/projects/WFXM/butler-v5/scripts/typecheck-gate.sh
```

Expected: 退出码 0；若 deadcode 报出使用项则定位并删除。

### Task 8: domain 零依赖门禁

**Files:**
- Create: `butler-v5/tests/architecture/domain-zero-io.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest"
import { execFileSync } from "node:child_process"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const domainRoot = join(process.cwd(), "packages/domain/src")

function listTs(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    const st = statSync(p)
    if (st.isDirectory()) out.push(...listTs(p))
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
  }
  return out
}

const FORBIDDEN = [
  /from\s+["']effect["']/,
  /from\s+["']drizzle/,
  /from\s+["']postgres/,
  /from\s+["']node:fs/,
  /from\s+["']node:http/,
  /from\s+[""]\.\.\/\.\.\/ports/,
  /from\s+[""]\.\.\/\.\.\/infrastructure/,
  /from\s+[""]\.\.\/\.\.\/application/,
  /from\s+[""]\.\.\/\.\.\/adapters/,
]

describe("domain zero I/O", () => {
  it("forbids infrastructure imports", () => {
    const files = listTs(domainRoot)
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      for (const pat of FORBIDDEN) {
        if (pat.test(src)) violations.push(`${file}: ${pat}`)
      }
    }
    expect(violations).toEqual([])
  })
})
```

- [ ] **Step 2: 运行确认当前通过**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test tests/architecture/domain-zero-io.test.ts
```

Expected: PASS。若失败，定位并删除违例 import。

### Task 9: 依赖方向门禁

**Files:**
- Create: `butler-v5/tests/architecture/dependency-direction.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

function listTs(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    const st = statSync(p)
    if (st.isDirectory()) out.push(...listTs(p))
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p)
  }
  return out
}

function findPkgImports(src: string, layer: string): string[] {
  const re = new RegExp(`from\\s+["']@butler/${layer}`, "g")
  return src.match(re) ?? []
}

describe("dependency direction", () => {
  it("domain must not depend on ports/application/infrastructure", () => {
    const files = listTs(join(process.cwd(), "packages/domain/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "ports")).toEqual([])
      expect(findPkgImports(src, "application")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
  it("ports may import only domain types", () => {
    const files = listTs(join(process.cwd(), "packages/ports/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "application")).toEqual([])
      expect(findPkgImports(src, "infrastructure")).toEqual([])
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
  it("application must not import adapters", () => {
    const files = listTs(join(process.cwd(), "packages/application/src"))
    for (const file of files) {
      const src = readFileSync(file, "utf8")
      expect(findPkgImports(src, "adapters")).toEqual([])
    }
  })
})
```

- [ ] **Step 2: 运行确认**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test tests/architecture/dependency-direction.test.ts
```

Expected: PASS。若失败，需拆出反向依赖或重新归类（受保护文件 `packages/ports/src/index.ts` 在 off-limits 列表中，类型扩展只能追加在末尾）。

### Task 10: 统一 `pnpm gate` 脚本

**Files:**
- Modify: `butler-v5/package.json`

- [ ] **Step 1: 增强 `gate` 脚本**

修改 `butler-v5/package.json` 中 `gate` 为：

```json
"gate": "pnpm format:check && pnpm typecheck && pnpm lint && pnpm test -- --coverage && bash scripts/typecheck-gate.sh"
```

- [ ] **Step 2: 验证**

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 gate
```

Expected: 全部步骤退出码 0。若有失败，按失败位置修复后再跑。

### Task 11: CI 工作流同步

**Files:**
- Modify: `butler-v5/.github/workflows/ci.yml`

- [ ] **Step 1: 同步 Postgres 版本和 gate**

把 `ci.yml` 中 `test` job 的 `pnpm test -- --coverage` 改为：

```yaml
- run: pnpm gate
```

并在 `lint-and-typecheck` job 增加：

```yaml
- run: bash scripts/typecheck-gate.sh
```

- [ ] **Step 2: 验证（本地干跑）**

```bash
docker compose -f /home/ailearn/projects/WFXM/butler-v5/docker-compose.yml up -d postgres
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test
docker compose -f /home/ailearn/projects/WFXM/butler-v5/docker-compose.yml down
```

Expected: 测试运行通过。

### R1 退出条件

- `pnpm gate` 在本地通过；
- Vitest 不再有重复收集；
- ESLint 不再因 `parserOptions.project` 失败；
- domain 零 I/O 与依赖方向门禁全绿；
- CI 工作流与本地 `gate` 等价。

---

## R2: Domain + Contracts（详细子计划将在进入 R2 前拆出）

**目标交付物：**
- `packages/domain/` 下各上下文（conversation/turns/tools/workflows/projects/memory/permissions/approvals/events/errors）的纯 ADT、状态机和 Projection。
- `packages/contracts/`：API/Event/Plugin Manifest 的 schema。
- 增量补齐 `Application UseCase` 接口（`StartConversation`/`SubmitUserMessage`/`RunTurn`/`ApproveRequest`/`RejectRequest`/`StartWorkflow`/`ResumeWorkflow`/`DelegateTask`/`AcceptMemory`/`SearchProjectKnowledge`/`ActivateProject`/`ImportV4Assets`/`RebuildProjection`）。

**规划模板：**

1. 为每个上下文新增 `pure.ts` + `pure.test.ts` + `types.ts` + `index.ts`。
2. 先写状态机、纯函数、`Result<Decision, LoopError>` 类转换。
3. `types.ts` 定义 `EventEnvelope`、`CapabilityLease`、`ModelDecision` 等共享类型。
4. 契约测试 `tests/contracts/test_domain_event_schema.test.ts` 验证事件 envelope。
5. 拒绝任何 `import { Effect, Layer, fs, http, drizzle }` 进入 `domain/`。

**退出门禁：**

- `pnpm gate` 全绿；
- `tests/architecture/domain-zero-io.test.ts` 通过；
- 事件 schema 锁定版本。

---

## R3: Persistence Kernel（详细子计划将在进入 R3 前拆出）

**目标交付物：**
- `migrations/` 下的 PostgreSQL schema：events、outbox、audit_events、projections、blobs、snapshots。
- `packages/infrastructure/src/persistence/eventstore-live.ts` 真实实现：
  - `append`/`load`/`subscribe`；
  - 乐观并发（`streamId + streamVersion`）；
  - `outbox.enqueue` 在同一事务内追加。
- `packages/infrastructure/src/projections/` 至少一个 projection（如 `ConversationListProjection`）。
- 崩溃恢复与幂等：Worker `claim`/`lease`/`deliver`/`retry`/`dead-letter`。

**最小任务：**

1. Task: 写 `migrations/0001_event_store.sql`。
2. Task: 写 `EventEnvelope` 入表函数 `append` 失败测试。
3. Task: 实现 `DrizzleEventStoreLive.append` 满足乐观并发。
4. Task: Outbox enqueue 与事件同事务。
5. Task: 崩溃恢复：写一个测试模拟进程崩溃后重新启动仍能续 run。
6. Task: Projection 重放：删表后从 events 重新构建。

**退出门禁：**

- 集成测试：Postgres container 下重放 1000 events 与崩溃恢复通过；
- 写锁竞争（同一 streamId 并发 append）无 race；
- 死信表正确入死信。

---

## R4: Agent Runtime（详细子计划将在进入 R4 前拆出）

**目标交付物：**
- `packages/runtime/`（新建）：`AgentKernel`、`TurnRunner`、`ContextManager`、`ModelRouter`、`DecisionDecoder`、`PolicyEngine`、`ToolRuntime`、`DelegateRuntime`、`MemoryRuntime`、`EventRecorder`。
- `ModelDecision` 解码与 bounded repair/retry。
- `ModelOutputRejected` 错误 ADT。
- `tests/runtime/`：fake LLM、fake Tool，覆盖单轮状态机所有路径。

**最小任务：**

1. Task: 在 `packages/domain/src/` 定义 `ModelDecision` ADT。
2. Task: 写 `DecisionDecoder` 单元测试。
3. Task: 实现 `DecisionDecoder.parse`。
4. Task: 写 `TurnRunner.runTurn` 状态机测试。
5. Task: 实现 `TurnRunner`，串联 `Context → Model → Decode → Policy → Tool`。
6. Task: 写 `ToolRuntime` 取消与超时测试。
7. Task: 实现 `ToolRuntime` 包装 Tool + 取消。
8. Task: 写 `DelegateRuntime` 能力传递测试。
9. Task: 实现 `DelegateRuntime`。

**退出门禁：**

- fake LLM 下能跑通 6 种 `ModelDecision` 路径；
- 取消、超时、retry、budge 边界都覆盖；
- 不允许任何 LLM 直连 adapter 的代码路径。

---

## R5: Adapters + Delivery（详细子计划将在进入 R5 前拆出）

**目标交付物：**
- `packages/adapters/postgres/` 包装 Drizzle 实现 `EventStoreService`、`OutboxService`、`ProjectionStore`。
- `packages/adapters/llm/`：Anthropic、OpenAI 兼容、Provider failover、Token 计量。
- `packages/adapters/wechat/`：iLink QR 登录、消息收发、签名校验。
- `apps/api/`：HTTP 入口（`POST /turn`、`GET /conversations`）。
- `apps/wechat-gateway/`：微信入站/出站进程。
- `apps/worker/`：Outbox/Projection/Scheduler/Memory 进程。
- `apps/cli/`：命令转发。
- `compose.yaml`：postgres + pgvector + 三个 app。

**最小任务：**

1. Task: 抽离 `adapters` 包，迁移现有 `infrastructure/src/llm`、`wechat`、`persistence`、`mcp` 到子包。
2. Task: 写 HTTP API handler 测试。
3. Task: 实现 `POST /turn`。
4. Task: WeChat adapter 真实 iLink 接入。
5. Task: Worker process 启动。
6. Task: Compose 起 4 个进程并 e2e。

**退出门禁：**

- 端到端：CLI → API → Worker → EventStore → Projection → WeChat 文本回包，全程 E2E 通过；
- Provider 故障切换：杀掉 primary 后请求自动走 fallback；
- Compose 重启后状态可恢复。

---

## R6: Migration + Shadow（详细子计划将在进入 R6 前拆出）

**目标交付物：**
- `packages/migration/v4-importers/`：项目、MEMORY、任务、审批、Skill、经验。
- `packages/migration/shadow/`：从 v4 读取脱敏入站事件、生成 v5 Decision、对比、报告。
- `scripts/run-migration-dry-run.sh`、`scripts/run-shadow-week.sh`。

**最小任务：**

1. Task: 写 `ProjectImporter` 测试：解析 v4 `project.yaml`。
2. Task: 实现 `ProjectImporter`。
3. Task: 写 `MemoryImporter` 测试：解析 `MEMORY.md`。
4. Task: 实现 `MemoryImporter`。
5. Task: 写 `ShadowRunner` 测试：相同入站事件应产生与 v4 决策等价。
6. Task: 实现 `ShadowRunner` 报告。
7. Task: 1 周 shadow 实跑 + 报告。

**退出门禁：**

- 核心资产 dry-run 拒绝项全部有人工处置；
- Shadow 核心场景成功率 ≥ 95%；
- Shadow 高风险越权漏拦截 = 0。

---

## R7: Cutover + Retirement（详细子计划将在进入 R7 前拆出）

**目标交付物：**
- `scripts/v4-snapshot.sh`：在切换窗口前冻结 v4 状态。
- `scripts/cutover.sh`：执行 R0 已设计好的 cutover 步骤。
- `scripts/rollback.sh`：v4 回滚。
- `archive/v4/`：把 v4 根目录移入只读参考目录。

**最小任务：**

1. Task: 写 v4 snapshot 脚本（dump Postgres + `.butler/` + 项目数据 + 校验 manifest）。
2. Task: 写 cutover 脚本，串行执行：v4 read-only → 增量迁移 → manifest 校验 → v5 启动 → 微信切换。
3. Task: 写 rollback 脚本。
4. Task: 演练：dress-rehearsal 在非生产环境跑一次 cutover + rollback。
5. Task: 把 `archive/v4/` 移入并加 README。
6. Task: 把所有文档 SSOT 指向 v5。

**退出门禁：**

- Cutover 在非生产环境演练成功，rollback 演练成功；
- v4 不再处理生产流量；
- 所有文档 SSOT 指向 v5；
- ADR-0001 标记为“Completed”。

---

## 完成定义（再确认）

与 `2026-08-08-wfxm-rearchitecture-design.md` 14 节一致：v5 是唯一活动主线；v4 不再处理生产流量；核心资产迁移报告完整；v5 强制门禁全绿；Event Store 可重放；Projection 可重建；PostgreSQL 可备份恢复；Outbox 与 dead-letter 可运维；微信主流程与审批通过 E2E；Provider 故障切换通过；权限绕过测试为 0；v4 归档为只读参考；所有文档以 v5 为 SSOT。

## 与规格的覆盖检查

- 规格 1.1 已确认决策：R0 包含 ADR-0001。
- 规格 3.1 产品目标：R4/R5/R6 覆盖微信、API/CLI、项目、LLM、Agent Turn、工具、审批、委派、Workflow、MEMORY、任务、Event Store、迁移、诊断。
- 规格 4.2 硬边界：R1 门禁、Task 8/9 强制。
- 规格 6.1 模型输出边界：R4 落地 `ModelDecision` ADT。
- 规格 7.2 Event Envelope：R3 落地。
- 规格 8.1 Capability Lease：R4 落地。
- 规格 12.1 迁移资产：R6 覆盖。
- 规格 13 阶段顺序：R0–R7 完整覆盖。
- 规格 14 完成定义：作为最终退出门禁。
