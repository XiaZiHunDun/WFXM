# Phase 2 · T1 测试清理记录（2026-11-19）

> 对应任务书：[`phase2-test-eval-system-2026-11-19.md`](./phase2-test-eval-system-2026-11-19.md) §2 / §9 T1
> 本文件记录：section 守卫的映射与删除清单、命令测试合并方式、发现的缺陷与覆盖缺口。
> 生产代码零改动。

## 1. 结构不变量：24 → 0 个 `section*` 文件

原 24 个章节守卫（4606 行）全部删除；其中有价值的结构约束已并入 8 个不变量文件。
不变量文件本身不新增依赖，全部可离线运行。

| 原文件 | 去向 / 处理 |
|--------|-------------|
| `section3-dependency-rules` | #1/#4 → `dependency-direction.test.ts`（含相对路径写法、policy-gate SDK 隔离）；#2/#3/#6 → `apps-layer-boundaries.test.ts`；#5 → `side-effect-throat.test.ts` |
| `section5-domain-pure` | → `domain-zero-io.test.ts`（域层零项目依赖、零 Node 内置） |
| `section6-application-orchestrator` | RunEngine 唯一声明 → `side-effect-throat.test.ts` |
| `section7-ports-main` / `7-1-model-port` / `7-1-port-snapshot` / `7-1-repository` | 依赖方向 → `dependency-direction.test.ts`；Model Port / Repository 行为由 `packages/ports/src/core/model-port.test.ts`、`runtime-store.cross-impl.test.ts` 等功能测试覆盖。`r2-shim` 生产引用检查由 §15 超时守卫间接保留（生产文件不得 import）。 |
| `section8-9-adapters-boundary` | TriggerSource/builders 由 `packages/domain/src/runtime/run-trigger.test.ts` 覆盖；“Model/Channel 不得注册为 Capability” → `capability-no-auto-grant.test.ts` |
| `section10-governance-arch-guard` | 行为由 `policy-gate.test.ts`、`capability-boundary.test.ts` 覆盖；ACK 文本字段形状不再守卫（见 §3 缺口） |
| `section10-4-6-13-deep-audit` | ModelDecision 5 tag 由 `decision` 功能测试覆盖；sandbox profile 字段形状不守卫（见 §3） |
| `section11-deferred-triggered` / `11-1-2-3-current-state-immutable` | 表存在性/路由计数属实现形状，功能由 task/document/procedure store 测试覆盖；删除（见 §3） |
| `section12-knowledge-memory` | 三层/去重/自动晋升/候选过期均有领域功能测试覆盖；表字段形状不守卫（见 §3） |
| `section14-token-cost` / `14-observability-fields` / `14-costusd` | 计费与 trace 行为由 `apps/api/src/llm-pricing.test.ts`、`packages/domain/src/observability/local-trace.test.ts` 覆盖；字段形状不守卫（见 §3） |
| `section15-effect-discipline` | → `single-llm-tool-loop.test.ts`（`completeWithTimeout`、直连调用必须有超时、adapter 不自带超时策略） |
| `section16-process-boundary` | → `workspace-sandbox-arch.test.ts`（子进程运行器不得 import Core） |
| `section17-1-2-monorepo-management` / `17-3-orphan-package` | → `package-membership.test.ts`（无孤儿包、恰好 5 个活跃包） |
| `section18-trigger` | 未触发特性守卫删除（见 §3） |
| `section20-invariants-batch-a` | #1 → `side-effect-throat.test.ts`；#2/#3/#4 → `dependency-direction.test.ts` + `apps-layer-boundaries.test.ts` |
| `section20-invariants-batch-b` | #6/#13 行为由 `run-engine.test.ts`、`wechat-active-run-conflict.test.ts` 覆盖；#15 为一次性交接决策，删除 |

### 额外删除（非 section，但已失效/重复）

| 文件 | 行数 | 理由 |
|------|------|------|
| `tests/guard/no-layer-violation.test.ts` | 178 | 与 `dependency-direction.test.ts` 重复且更弱（只查 `@butler/*` 字符串） |
| `tests/architecture/r2..r6-end-to-end.test.ts` | 205 | 5 个文件已被 `vitest.config.ts` exclude，从未在任何 CI 中执行；同步移除 exclude 条目 |
| `apps/api/src/wechat-inbound-commands.test.ts` / `wechat-memory-commands.test.ts` / `wechat-subagent-commands.test.ts` | 534 | 合并进 `apps/api/src/wechat-commands.test.ts`（共享 `tests/wechat-command-harness.ts`），并删除 2 条与 `wechat-quality-gate.test.ts` 重复的 /验 用例 |

保留：`wechat-task-commands.test.ts`（任务生命周期）、`wechat-undo-command.chain.test.ts`（撤销链）。
两者是独立子系统而非样板重复，强行并入会突破「单文件 ≤400 行」约束。

## 2. 数量变化

| 指标 | 清理前 | 清理后 | 变化 |
|------|--------|--------|------|
| 测试文件 | 314 | 282 | -32 |
| 测试行数 | 47,302 | 42,356 | -4,946（-10.5%） |
| `tests/architecture/section*` | 24 文件 / 4,606 行 | 0 | -100% |
| 命令测试样板 | 5 文件 / 1,352 行 | 3 文件 / 1,076 行 | -276 |

整体降幅 10.5%，未达任务书的 15%。剩余降幅依赖 T2–T5 用契约/集成套件替换重叠的旧断言，
不再为凑数字删除仍有语义的用例（任务书 §9「禁止为了绿而放宽断言」）。

## 3. 发现的缺陷与覆盖缺口

### F-01 LLM 调用缺少单次超时（记录，不在本任务修）

`apps/api/src/butler-assembly.ts` 的 `createButlerModelPort` 直接
`Effect.runPromise(adapter.complete(...))`，没有 `Effect.timeout`。
pi 引擎只在任务级设置 abort 定时器，单次模型调用可能长时间挂起。
`single-llm-tool-loop.test.ts` 暂以 `KNOWN_UNBOUNDED` 白名单放行并指向本条。

### 已移除、暂无等价静态守卫的约束（靠功能测试或产品决策兜底）

| 约束 | 为何移除 | 现在的兜底 |
|------|----------|------------|
| §11 表存在性（tasks/procedures/documents）、无 approvals 表 | 断言 schema 形状，重构即误报 | task/document/procedure store 功能测试 |
| §12 DurableMemory 四字段、无 embedding 列 | 同上 | `knowledge/*.test.ts` |
| §14 TraceEvent / LLMUsage 字段形状 | 同上 | `llm-pricing.test.ts`、`local-trace.test.ts` |
| §10 PolicyDecision / ActionRequest / ScopedGrant 字段清单 | 同上 | `policy-gate.test.ts`、`capability-boundary.test.ts` |
| §18 未触发特性（projection/embedding/snapshot）不得被引用 | 属产品触发决策，功能上线时必然失败 | 发布评审；如需恢复应改为「触发器检查清单」而非测试 |
| §0「不存在进程内 EventBus」 | 一次性架构决策 | code review |

## 4. T2–T5 新增契约/集成套件

| 层 | 文件 | 用例数 | 锚点 |
|----|------|--------|------|
| L1 工具 | `tests/contracts/tools/workspace-tools.contract.test.ts` | 47 | list_dir/read_file/write_file/run_command/send_wechat_file 的入参、错误 envelope、路径逃逸、大小预算、退出码 |
| L1 工具 | `tests/contracts/tools/pi-native-tools.contract.test.ts` | 51 | read/write/edit/bash/grep/find/ls 的必填参数、逃逸、边界、截断、超时 |
| L1 消息 | `tests/contracts/messages/normalize-inbound.contract.test.ts` | 71 | wechat/channel 规范化的形态矩阵、错误 kind、幂等键规则 |
| L1 消息 | `tests/contracts/messages/outbound-render.contract.test.ts` | 20 | 回复可发送性：截断、兜底、术语替换、分条 |
| L1 状态 | `tests/contracts/state/run-state.contract.test.ts` | 12 | 迁移矩阵、终态不可回退、double-completion、版本冲突、到期/级联 |
| L1 状态 | `tests/contracts/state/idempotency.contract.test.ts` | 5 | 重复入站/run 幂等键、并发重复投递、不同消息独立 |
| L1 状态 | `tests/contracts/state/approval.contract.test.ts` | 6 | 待审批落库、确认/拒绝/重复确认/过期、外部取消 |
| L1 状态 | `tests/contracts/state/migration.contract.test.ts` | 2 | 空库到最新 schema、旧数据迁移后关键行可读 |
| L2 集成 | `tests/integration/butler-main-chain.integration.test.ts` | 6 | 纯文本/write_file/read_file/run_command/工具失败/越界写的用户可见结果 + DB 终态 |
| L2 集成 | `tests/integration/butler-resilience.integration.test.ts` | 6 | 重复 messageId、审批拒绝、空/超长内容、LLM 空响应、非法 toolCall |

合计 10 文件 / 233 个用例。全部离线可跑，未改动生产代码与已有测试。
`pnpm test`：295 文件 / 2336 通过 / 2 skipped。

## 5. T2–T5 期间发现的缺陷（记录，未修）

### F-02 终态 Run 被同幂等键重投后复活并重复执行（已修复）

`RunEngine.executeInbound` 在既有 run 已 `succeeded` 时，`createRun` 幂等返回旧 run，
随后仍无条件迁移到 `running` 并再次执行 runBody。同一幂等键二次投递时 runBody 执行两次，
run 行数仍为 1，但 version 从 3 被推到 5。破坏“重复消息只处理一次”的副作用契约。
由 `tests/contracts/state/idempotency.contract.test.ts` 的直连 store/engine 用例暴露；
butler 层 `replayDuplicateInbound` 会先拦截，所以集成用例未复现。

**修复**：`executeInbound` 在 `createRun` 后检查 `isTerminalRunStatus`，命中则抛
`CompletedMainRunReplay`，不再迁移/执行；butler loop 捕获后返回「这条消息已经处理过了」。
回归用例：`idempotency.contract.test.ts` 的 `rejects a duplicate delivery whose run already completed instead of re-executing (F-02)`。

### F-03 `createWaitingApprovalStep` 绕过状态机

直接调用 `store.transitionRunStatus(..., "waiting_approval")`，未走 `canTransitionRun`；
若误用于终态 run，会把终态改写为 `waiting_approval`。

### F-04 channel 入口幂等键分叉

无 `messageId` 时 `NormalizedInbound.idempotencyKey = channel-{conversationId}-turn-{nowMs}`，
而 `runTrigger.idempotencyKey = channel-{channelId}-{conversationId}`。同一入站存在两个键，
取决于下游用哪一个去重。

### F-05 空 content 在规范化层被接受

`content: ""` 返回 `ok: true`，空消息继续流入 LLM/兜底路径，而不是在 intake 拒绝。

### F-06 控制字符可直达出站

`finalizeReply("\u0000\u0007")` 不被判为“空回复”，会原样发送不可见控制字符（仅纯空白走兜底）。

### F-07 `splitForWechat` 可能切断 emoji 代理对

按 UTF-16 码元硬切，边界落在 emoji 内部时每段产生孤立代理项，微信/iLink 侧可能显示替换字符或拒收。

### F-08 最终出口未过滤 `mcp_` / 原始工具名

`sanitizeForWechat` / `finalizeReply` 只替换「子代理 / Durable Memory / Project Knowledge」，
模型正文里的 `mcp_...` 等工具标识会直接到达用户；仅审批文案走 `toolActionLabel` 兜底。

### F-09 write_file 审批后失败直接终结 Run

`shouldFailRunAfterCapability` 对无 `exitCode` 的失败返回 true，`resumeApprovedCapability` 随即
`failRun`，用户只收到泛化文案“审批后执行失败，请稍后重试”，LLM 没有机会解释或给替代方案；
与 run_command 非零退出可继续对话的语义不一致。

### F-10 审批成功后的回复未作为 assistant 消息落库

`continueLoopAfterCapability` 的 exec 直返路径只写 `steps`/`result`，不调用 `appendMessage`；
审批确认后的回复无法通过会话消息回放，重投只会得到“这条消息已经处理过了”。

### F-11 pi-native `read` 对真正空文件输出 `"     1 | "`

代码里 `(empty file)` 的回退只在切片为空时触发，而 `"".split("\n")` 得到 `[""]`。
契约测试按实际输出断言（`bytes=0` + 单行编号），未改实现。

### F-12 审批提示暴露原始工具名（已修复）

写文件审批时用户可见文案为「需要 write_file 操作 ../../leak.txt，请确认」，
直接暴露内部工具名（`write_file`）。`sanitizeForWechat` 只替换了少数术语，
`userMessage.noRawTool` 也只匹配「待执行：(write|edit|...)」这一种格式。
轨迹 `traj-018-write-escape` 按当前语义断言为「请求审批且不执行」，
未把原始工具名泄漏作为通过条件；该泄漏需要产品侧统一改为中文动作名。

**修复**：`packages/domain/src/governance/types.ts` 的 `approvalQuestion` 增加核心工具中文标签
（write_file/edit_file/apply_patch → 修改文件，run_command → 执行命令 等）；未知内部
snake_case 能力降级为「需要执行一项操作，请确认」，不再回显 token。MCP 路径保持原样。
回归用例：`types.test.ts` 的核心工具标签与未知 token 两条；轨迹 `traj-018` 增加
`mustNotMatch: ["write_file"]`。

## 6. T6–T8 评测资产

### T6 轨迹集（18 条）

- 位置：`tests/trajectories/*.json`（数据在 WFXM）
- 执行：`agent-eval` 的 `src/trajectory.mjs` 归一化为 EvalTask，交给既有 `wfxm` adapter
  （`scripts/eval/run-task.ts`）跑真实 `/v1/wechat/inbound` 路径；判定复用 `verify.mjs`。
- 分组：主链路 4、消息形态 3、状态/幂等 4、失败注入 5、安全 2。
- 只允许结果断言：`toolSetIncludes/Excludes`、`finalDecisionIn`、`reply.mustMatch/mustNotMatch`、
  `files`、`budget.maxLlmCalls`；`toolSequence/llmCalls/promptContains` 会在加载时直接报错。
- 验证：`WFXM_ROOT=/home/ailearn/projects/WFXM node src/cli.mjs run --suite trajectory --runtime wfxm`
  → 18/18 通过。

### T7 开放任务（20 条）

- 位置：`agent-eval/tasks/butler-open/*.json`；评分：`agent-eval/src/judge.mjs`。
- 类别：代码理解 4、只读检索 4、小改动 5、多步 4、澄清/拒绝 3。
- 评分顺序：`rubric.hard`（产物文件、工具集合、测试通过、预算）全部通过后，
  才调用固定 judge（1–5 分，缺省均值 ≥4）；未配置 judge 时记录 `judge.pending`，
  不把「未评分」当成失败。
- 首轮只记基线；CI 仅在存在模型密钥时运行 L4。

### T8 CI 分层

- WFXM `ci.yml`：L0 结构不变量 → L1 契约（tests/contracts）→ L2 集成（tests/integration）→ 全量测试。
- agent-eval `.github/workflows/nightly.yml`：每晚跑 L3 轨迹 + butler fixture；
  有 `MINIMAX_API_KEY` 时追加 L4 开放任务；产物 `.eval-runs` 归档。

### 观察（非缺陷，记录语义）

- 超长消息由 `detectSpam` 在 `executeInbound` 之前短路，DB 不创建 Run；用户仍收到可读提示。
- `run_command` 输出截断按“整块丢弃超限 chunk”实现，实际输出可能略小于 32KiB，但截断标记存在。

## 7. F-01 / F-03～F-11 修复记录（2026-11-19）

| 缺陷 | 修复 | 回归 |
|------|------|------|
| F-01 单次 LLM 调用无超时 | `createButlerModelPort` 用 `Effect.timeout(BUTLER_V5_LLM_TIMEOUT_MS, 默认 30s)` 包住每次 `adapter.complete`；从超时守卫白名单移除 | `single-llm-tool-loop.test.ts` |
| F-03 审批绕过状态机 | `createWaitingApprovalStep` 先 `canTransitionRun(run.status, "waiting_approval")`，否则抛 `IllegalRunTransitionError` | `approval.contract.test.ts`「refuses to move a terminal run back」 |
| F-04 channel 幂等键分叉 | 统一为 `messageId ?? channel-{channelId}-{conversationId}-{turnId}`，并作为 `messageId` 传入 `buildChannelRunTrigger` | `normalize-inbound.contract.test.ts` 键矩阵 |
| F-05 空内容进入 LLM | 两个入口对 `content.trim() === ""` 返回 `invalid_body` | 键矩阵新增空/纯空白拒绝 |
| F-06 控制字符直达出站 | `sanitizeForWechat` 剥离 C0/C1（保留 `\n`/`\t`），仅剩控制字符时走兜底 | `outbound-render.contract.test.ts` |
| F-07 emoji 代理对被切断 | `splitForWechat` 在代理对边界回退一码元，拼接与原文一致 | `outbound-render.contract.test.ts` |
| F-08 原始工具名/mcp_ 泄漏 | 出口把 `mcp_*` 替换为「外部工具」，已知 snake_case 工具名替换为中文动作 | `outbound-render.contract.test.ts` |
| F-09 审批后工具失败终结 Run | 删除「无 exitCode 即 failRun」分支；失败作为工具结果交回模型；无模型时回「操作没有完成：…」 | `butler-main-chain.integration.test.ts` |
| F-10 审批回复未落库 | `continueLoopAfterCapability` 的 exec-direct / tool-fallback 分支补 `appendMessage(assistant)` | `approval-resume.test.ts` |
| F-11 空文件显示空行号 | `read` 对 `byteLength === 0` 返回 `(empty file)` | `pi-native-tools.contract.test.ts` |

注意：F-08 会影响任何把原始工具名当作「用户可见文案」的旧断言——验收场景
`F2-sensitive` / `C-F2-checklist-proceed` 已改为断言中文动作「发送文件」。
