---
date: 2026-08-28
produced: [shift-card]
---

# Butler v5 — R16 Sandbox bwrap 扩面（part-1 闭环 / part-2 待 operator manual override）

## 项目当前态（part-1 闭环后）

- **HEAD**：origin/main = `f7477386`（R15 `1d5013df` 之上 + 4 commits）
- **5 gate**：
  - `pnpm typecheck` ✅（10 packages 0 errors）
  - `pnpm lint` ✅（0 warnings / --max-warnings 0）
  - `pnpm test` ✅ `188 files / 1106 pass / 1 skip / 0 fail`（基线 1096，+10 net）
  - `pnpm test:archived` ✅ `19 files / 83 pass / 0 fail`
  - R16 architecture guard: `mcp-spawn-arch.test.ts` 1/1 pass；`workspace-sandbox-arch.test.ts` 1/3 pass（**2 fail 是 R16.3 待办**——见下）
- **R16 commit 链**（4 commits）：
  | Commit | 摘要 |
  |---|---|
  | `2a2ea2cc` | sandbox(bwrap): add readOnly + executeWriteInSandbox + DENY ceiling for read/write |
  | `5cd5e660` | sandbox(mcp): gate MCP stdio spawn behind BUTLER_V5_SANDBOX=bubblewrap |
  | `f7477386` | test(arch): guard MCP bwrap gate + workspace-tools sandbox wiring |
- **DESIGN §5.5 状态**：本班 *part-1* 闭环（MCP stdio + bwrap primitive + ceiling + arch guard）。*part-2*（workspace-tools.ts read_file/write_file dispatch）卡在 v5 AI guard PROTECTED_FILES，需 operator `[MANUAL-OVERRIDE]`。

## R16.3 — operator manual override 待办

### 为什么 AI 工具不能直接改

`scripts/ai_guard/pre_tool_use_hook.py:52` 把 `butler-v5/apps/api/src/workspace-tools.ts` 列入 PROTECTED_FILES（set 30-53）。PreToolUse hook 拦 `Edit`/`Write`，返回：
```
文件 butler-v5/apps/api/src/workspace-tools.ts 是核心受保护文件，禁止 AI 工具直接修改。
如需修改，请先在 GitHub 创建 issue 说明原因，由人工修改并运行完整门禁。
```

### Apply 命令（精确）

```bash
# 1. 拉 main（含 patch 文件）
cd /home/ailearn/projects/WFXM
git pull origin main

# 2. 应用 patch（git apply --check 已验证 forward OK）
git apply .blackboard/shifts/2026-08-28-r16.3-workspace-tools.patch

# 3. 验证
cd butler-v5
CI= pnpm test -- workspace-sandbox-arch    # 期望 3/3 pass
CI= pnpm test                                # 期望 1106 pass
CI= pnpm typecheck && CI= pnpm lint          # 期望 0 错 / 0 警告

# 4. commit（per R9.5/R7.5/R11.1 protocol：--no-verify；message body 不写裸反引号 SHA）
git add butler-v5/apps/api/src/workspace-tools.ts
git commit --no-verify -m "sandbox(workspace): dispatch read_file/write_file through bwrap (R16.3 manual override)" \
  -m "R16 part-2 closure. workspace-tools.ts:115-179 makeReadFileTool +
makeWriteFileTool 接 R16.2 的 executeArgvInSandbox。Read 路径 cat-equivalent
(readOnly=true → workspace --ro-bind)；Write 路径 tee-equivalent
(stdinContent 透传)。disabled 模式 fall back 进程内 fs 行为，与 run_command
模式一致。R16.3 由 operator [MANUAL-OVERRIDE] apply（v5 AI guard
PROTECTED_FILES 拦 AI 直接改）。patch 源文件
.blackboard/shifts/2026-08-28-r16.3-workspace-tools.patch（已落 main）。"

# 5. push
git push origin main
```

变更概要（hunk-level）：
- makeReadFileTool（line 115-）：in-process `statSync + readFileSync` → `executeArgvInSandbox({ argv: ["cat", "--", resolved.path], readOnly: true, ... })`；disabled 模式 fall back to 原 in-process 行为。
- makeWriteFileTool（line 145-）：in-process `mkdirSync + writeFileSync` → `executeArgvInSandbox({ argv: ["tee", resolved.path], stdinContent: rawContent, ... })`；disabled 模式 fall back to 原 in-process 行为。
- 不修改：原 import 块、注释、`sandboxWorkspaceRootFrom`、`ALLOWED_RUN_COMMANDS`、`makeRunCommandTool`（已 wired 形态）。

### 必须做的事（R16.3 closure）

`workspace-tools.ts` 的 `makeReadFileTool`（line 115-143）+ `makeWriteFileTool`（line 145-179）改为 dispatch 通过 `executeArgvInSandbox`（R16.2 helper 已就绪）：

**Read 路径**：
- `argv: ["cat", "--", resolved.path]`
- `readOnly: true`（workspace bind 用 --ro-bind，防意外写）
- `profileName: currentSandboxProfileName()`（来自 `@butler/runtime/sandbox/index.js`）
- `networkAllowlist: currentNetworkAllowlist()`
- `env: process.env`
- `runner: createDefaultProcessRunner()`（来自 `@butler/adapters/sandbox/bubblewrap-runner.js`）
- 当 `executeArgvInSandbox` 返回 `{mode: "disabled"}`（即 BUTLER_V5_SANDBOX !== "bubblewrap"）→ fall back 现有 in-process `statSync` + `readFileSync`（line 130-137 块）
- 当 `!ok` → `{ ok: false, reason: sandboxed.reason ?? "sandbox failed" }`
- 当 `ok` → `{ ok: true, output: sandboxed.stdout ?? "" }`

**Write 路径**：
- `argv: ["tee", resolved.path]`
- `stdinContent: rawContent`（触发 R16.2 `executeWriteInSandbox` 分支）
- 其他同 read 路径
- disabled 模式 fall back 现有 in-process `mkdirSync` + `writeFileSync`（line 168-169）
- `!ok` → reason；`ok` → `wrote {path} ({n} chars)` 输出

参考实现：同文件 `makeRunCommandTool`（line 181-267 line 251-264 块）已有的 disabled-mode fallback 模式。

### 验证

落 main 后后，本仓库 `tests/architecture/workspace-sandbox-arch.test.ts` 应自动 3/3 pass：
- 测试 1：`workspace-tools.ts` imports `@butler/adapters/sandbox/bubblewrap-runner.js`
- 测试 2：`makeReadFileTool` 块内有 `executeArgvInSandbox`
- 测试 3：`makeWriteFileTool` 块内有 `stdinContent`

5-gate 全绿（除上述 arch test 外，expected 1106 pass 与已闭环一致）。

### 已写但 AI 不动的部分

`apps/api/src/workspace-tools.bubblewrap.test.ts` 当前没有 R16 read/write bwrap 集成测试；建议 operator 落 R16.3 时同步加 `describe.skipIf(!bwrapAvailable)("makeReadFileTool under bubblewrap")` 与 `("makeWriteFileTool under bubblewrap")` 块（参考 line 43-173 已有 run_command 模板）。

## R16 决策 recap（plan agent + user lock）

| Q | 决策 |
|---|---|
| Q1 null profile | `profiles.ts:54` 显式补 read_file/write_file → DENY |
| Q2 fail-closed | 全部 fail-closed（与 `runInBubblewrap:411-413` 对齐） |
| Q3 readOnly 表达 | `buildBubblewrapArgs` 加 `options.readOnly?: boolean` |
| Q4 write stdin pipe | 新增 `executeWriteInSandbox` helper（inline spawn） |
| Q5 MCP path guard | inline spawn 旁路 `runInBubblewrap:403-405` argv[0] 校验 |
| Q6 MCP fallback | BUTLER_V5_SANDBOX unset → 裸 spawn（部署兼容） |

## 新会话必读（按顺序）

1. **本卡** ← 你正在读
2. `.blackboard/shifts/2026-08-28-r15-archived-rot-fix-handoff.md` —— R15（archived rot 修）上下文
3. `.blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md` —— R14 班段
4. `docs/plans/active/v5-architecture-alignment-handoff-2026-08.md` §5.5 —— 缺口定义（part-1 闭环 + R16.3 待办）
5. `.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-archived-test-rot-pattern.md` —— R15 教训
6. `.claude/projects/-home-ailearn-projects-WFXM/memory/feedback-v5-ai-guard-protected-files.md` ← **R16 新增**——v5 AI guard PROTECTED_FILES 拦截模式 + 流程

## 关键路径速查

| 用途 | 路径 |
|---|---|
| R16 commit 链 | `2a2ea2cc` → `5cd5e660` → `f7477386` |
| profiles ceiling（R16.1） | `butler-v5/packages/runtime/src/sandbox/profiles.ts:54` |
| bwrap primitive 扩面（R16.2） | `butler-v5/packages/adapters/src/sandbox/bubblewrap-runner.ts` （`buildBubblewrapArgs:293-311` + `BubblewrapRunInput.options?` + `executeWriteInSandbox`） |
| MCP spawn gate（R16.4） | `butler-v5/apps/api/src/mcp-spawn.ts` |
| Arch guard tests（R16.5） | `butler-v5/tests/architecture/mcp-spawn-arch.test.ts` + `workspace-sandbox-arch.test.ts` |
| R16.3 待办（R16 part-2） | `butler-v5/apps/api/src/workspace-tools.ts`（AI guard 拦，需 operator） |
| MCP spawn test | `butler-v5/apps/api/src/mcp-spawn.test.ts` |

## 不要做

延续 R14 + R15 不要做清单，新增强调：

- **不要让 AI 工具直接改 `workspace-tools.ts`**（v5 AI guard PROTECTED_FILES 拦，会卡 R16 part-2。本班已记录；操作员走 `[MANUAL-OVERRIDE]` 流程）
- 不要在 R16.3 commit body 写裸反引号 commit SHA（R13 教训）
- commit 用 `--no-verify`（R9.5/R7.5/R11.1 protocol）
- 不升 Channel Port 为 first-class（R13 §2.1 #4）
- 不复用 `_archive/{application,infrastructure,contracts}` 入生产
- 不为生产代码 import `r2-shim`
- 不为"架构完整"造休眠接口（DESIGN §7 + port-catalog §4）

## 下一步（待 user/operator 给题）

按 R15 handoff 候选不变，本班推进 R16 part-1（R16.3 仍待办）：
1. R16.3 closure（operator `[MANUAL-OVERRIDE]` apply workspace-tools.ts）
2. Channel Port 升 first-class（多个 channel 真接入后）
3. Model Port 立项（多 Provider 协议统一真出现时）
4. archived rot 修复已闭环
5. roadmap P5 段更新
6. 新能力 / 修 bug

## 失误清单（R16 新增 1 条）

1. **`mcp-spawn.ts` 误读 `options.env` 作为 bwrap gate 源** —— 初版写 `const env = options.env ?? process.env`，但 `options.env` 是子进程环境（caller 显式传 `{}` 时 bypass gate）。修法：始终从 `globalThis.process.env` 读（`hostEnv`），与 `executeArgvInSandbox` 的 host-side 读取模式一致（`workspace-tools.ts:254`）。`mcp-spawn.test.ts` test 1 抓到这个 bug。

R15 失误清单（保留）：
1. `test:archived` 不跑 typecheck 是 design vs 噪音权衡，不是 bug