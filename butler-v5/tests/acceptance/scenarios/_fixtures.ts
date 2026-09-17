/**
 * 真实 owner 任务场景集 — 用于 product-layer 行为分析。
 *
 * 设计原则：
 * - 每个场景 = `input` + `followUps` + `fixtures`（好 bot 行为）+ `expect`（断言 + 度量）
 * - fixture 是手工编码的"好 bot"应答序列（不是真 LLM，但反映 v5 已实现能力下的合理行为）
 * - 多 turn 时 fixtures 按 LLM 调用顺序消耗；counter 在 setFixtures 时重置
 * - 写文件触发 `WaitForApproval`；owner 后续「确认」走 inline approval
 *
 * 4 类共 52 场景（D67 T2a-2: +4 D 子分类场景 D-cross-channel-consistency /
 *   D-audit-correlation-continuity / D-owner-direct-no-inbound / D-additional-2）：
 * A. 真实开发任务（具体可执行）— 11（含 A11-session-digest-idle-return）
 * B. 开放性任务（探索型）— 10
 * C. 边界 / 失败模式 — 16（含 F1-fatigue / F2-sensitive / F3-replay / D67 T2a-1 ×4）
 * D. 跨场景组合 — 14（5 基础 + 5 chain-undo，D52 acceptance harness extension + D67 T2a-2 ×4）
 */
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { expect } from "vitest"
import {
  UNDO_CHAIN_CONV_FOR_TEST,
  UNDO_CHAIN_FOR_TEST,
  resetUndoChain,
  undoChain_listChainIds,
} from "@butler/api/workspace-tools.js"
import type { AcceptanceApp, FixtureEntry } from "../harness.js"

export type ScenarioCategory = "A-concrete" | "B-open" | "C-edge" | "D-combo"

export interface ScenarioExpect {
  /** reply 必须 match 的正则或子串（任一即可） */
  readonly replyPattern?: RegExp | string
  /** reply 必须全部包含的子串（D49: D1-chain-extension 用） */
  readonly containsAll?: readonly string[]
  /** reply 不能包含的子串 */
  readonly containsNone?: readonly string[]
  /** 期望 finalDecision（first turn） */
  readonly finalDecision?: "Respond" | "WaitForApproval" | "Finish"
  /** 期望至少触发的工具调用数（across all turns） */
  readonly minToolCalls?: number
  /** 是否期望走 approval flow */
  readonly requireApproval?: boolean
  /** 多 turn 场景：第 2+ turn 的 reply match */
  readonly followUpPatterns?: (RegExp | string)[]
}

/** D49: 透传给 setup/verify 钩子的上下文。 */
export interface ScenarioSetupCtx {
  /** acceptance harness 创建的临时 workspace 根目录。 */
  readonly workspaceRoot: string
  /** D67 T1b: harness app handle (F3-replay HTTP API direct call 用)。 */
  readonly app: AcceptanceApp
}

export interface Scenario {
  readonly id: string
  readonly category: ScenarioCategory
  readonly title: string
  readonly input: string
  /** 后续 turn（含 conversationId 复用） */
  readonly followUps?: readonly { readonly content: string }[]
  /** 多 turn 场景：第 2+ turn 的 reply match（pre-existing；ScenarioExpect.followUpPatterns 是同语义 alias）。 */
  readonly followUpPatterns?: (RegExp | string)[]
  readonly fixtures: {
    readonly plan?: readonly FixtureEntry[]
    readonly exec?: readonly FixtureEntry[]
    readonly intake?: readonly FixtureEntry[]
  }
  readonly expect: ScenarioExpect
  /** D49: 在 first turn 之前运行的钩子（用于 seed UNDO_CHAIN 等）。 */
  readonly setup?: (ctx: ScenarioSetupCtx) => Promise<void> | void
  /** D49: 在所有 turn 完成后运行的钩子（用于 verify 文件回写等）。 */
  readonly verify?: (ctx: ScenarioSetupCtx) => Promise<void> | void
}

const text = (content: string): FixtureEntry => ({
  content,
  toolCalls: [],
  stopReason: "end_turn",
})

const tool = (
  name: string,
  args: Record<string, unknown>,
  id = "tc-1",
): FixtureEntry => ({
  content: "",
  toolCalls: [{ id, name, args }],
  stopReason: "tool_use",
})

// 通用：read_file → 文本回复
const readThenReply = (path: string, summary: string): FixtureEntry[] => [
  tool("read_file", { path }),
  text(summary),
]

// 通用：write_file → 触发 approval（RunPauseForApproval）
const writeForApproval = (path: string, content: string): FixtureEntry[] => [
  tool("write_file", { path, content }),
]

// ============================================================================
// D67 T1b / D68 T2a — Acceptance harness audit writes.
// ============================================================================

/**
 * D68 T2a — D64 reader swap: fatigue reader now reads from
 * `runtimeStore.listRecentAuditEvents` (D66 T1a), not the subagent JSONL
 * log. So harness scenarios inject directly into the in-memory
 * `audit_events` table via `runtimeStore.appendAuditEvent` — that's the
 * canonical source the reader queries.
 *
 * Caller invokes this helper inside the scenario's `setup` callback,
 * passing the harness `ctx` so the in-memory store is reachable.
 */
async function injectAuditEvent(
  ctx: ScenarioSetupCtx,
  opts: {
    readonly toolName: string
    readonly parentConversationId?: string
  },
): Promise<void> {
  await ctx.app.wiring.runtimeStore.appendAuditEvent({
    auditId: crypto.randomUUID(),
    runId: null,
    conversationId: opts.parentConversationId ?? null,
    action: "tool_call",
    subject: opts.toolName,
    detail: { harnessInjection: "D68 T2a" },
    createdAt: new Date(),
    correlationId: null,
  })
}

/**
 * D68 T2a — Legacy no-op retained for backward compat with F2/C-F2
 * setups that called `freshSubagentAuditPath` to seed an empty JSONL.
 * After the reader swap, the JSONL is no longer read by the fatigue
 * reader, so setting the env override is dead code. Kept so existing
 * scenario definitions compile; `verify` callbacks still delete the
 * (never-set) env var harmlessly.
 */
function freshSubagentAuditPath(prefix: string): string {
  const auditTmpDir = mkdtempSync(join(tmpdir(), `butler-v5-${prefix}-`))
  const auditPath = join(auditTmpDir, "subagent.jsonl")
  process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] = auditPath
  return auditPath
}

// ============================================================================
// A. 真实开发任务（10）
// ============================================================================

export const scenariosA: readonly Scenario[] = [
  {
    id: "A1",
    category: "A-concrete",
    title: "读 README",
    input: "帮我读 /ws/README.md",
    fixtures: {
      plan: readThenReply(
        "/ws/README.md",
        "已读 README.md：项目是 butler-v5 — 函数式架构微信编码管家。主要功能：编码、会话记忆、微信入站。\n\n想深入看哪部分？",
      ),
    },
    expect: { finalDecision: "Respond", minToolCalls: 1, replyPattern: /README/ },
  },
  {
    id: "A2",
    category: "A-concrete",
    title: "改 user 路由支持手机号登录",
    input: "帮我改 user 路由支持手机号登录",
    fixtures: {
      plan: [
        tool("read_file", { path: "apps/api/src/routes/user.ts" }),
        // 好 bot 读完文件后建议 plan，触发 write_file 走 approval
        ...writeForApproval(
          "apps/api/src/routes/user.ts",
          "// 新增 phone 字段支持；add phone-based login flow\n...",
        ),
      ],
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 2,
      replyPattern: /确认|审批|approve/i,
    },
  },
  {
    id: "A3",
    category: "A-concrete",
    title: "跑 pnpm test",
    input: "跑 pnpm test 看有没有 fail",
    fixtures: {
      plan: [
        tool("run_command", { argv: ["pnpm", "test"] }),
        // P1 fix 2026-09-04: read-only run_command bypass approval
        text("已跑完。266 files / 1712 passed / 1 skipped，0 fail。"),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 1,
      replyPattern: /266|1712|pass/,
    },
  },
  {
    id: "A4",
    category: "A-concrete",
    title: "昨天我们改了什么",
    input: "昨天我们改了什么",
    fixtures: {
      plan: [
        text(
          "昨天（2026-09-03）我们 7 个 commit：\n1. test(acceptance) wechat end-to-end harness\n2. docs(plans) fix broken doc links\n3. chore gitignore .trae\n4. docs(superpowers) fill 2026-09-XX\n5. ci(butler-v5) explicit acceptance step\n6. chore(ai-guard) pre-commit hook sync\n7. chore(blackboard) record session close",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /commit|昨天/ },
  },
  {
    id: "A5",
    category: "A-concrete",
    title: "删 dead import",
    input: "把 packages/domain/src/foo.ts 里没人用的 import 删掉",
    fixtures: {
      plan: [
        tool("read_file", { path: "packages/domain/src/foo.ts" }),
        ...writeForApproval(
          "packages/domain/src/foo.ts",
          "// removed unused import\n...",
        ),
      ],
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 2,
    },
  },
  {
    id: "A6",
    category: "A-concrete",
    title: "timeout 可配",
    input: "把 utils.ts 的 timeout 改成可配的",
    fixtures: {
      plan: [
        tool("read_file", { path: "apps/api/src/utils.ts" }),
        ...writeForApproval(
          "apps/api/src/utils.ts",
          "// exported timeoutMs config; replaced hard-coded 30000 with cfg.timeoutMs\n...",
        ),
      ],
    },
    expect: { finalDecision: "WaitForApproval", requireApproval: true, minToolCalls: 2 },
  },
  {
    id: "A7",
    category: "A-concrete",
    title: "git log -5",
    input: "git log -5 给我看",
    fixtures: {
      plan: [
        tool("run_command", { argv: ["git", "log", "--oneline", "-5"] }),
        text(
          "最近 5 个 commit：\n09e0cdfb chore(blackboard)\nc4a0bcb8 chore(ai-guard)\n013d1095 ci(butler-v5)\nf3716d5f docs(superpowers)\n0f1ef949 chore",
        ),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 1,
      replyPattern: /commit/,
    },
  },
  {
    id: "A8",
    category: "A-concrete",
    title: "生成 PR 描述",
    input: "帮我写个 PR 描述，把最近 7 个 commit 整理出来",
    fixtures: {
      plan: [
        tool("run_command", { argv: ["git", "log", "--oneline", "-7"] }),
        text(
          "PR 描述草稿：\n## 摘要\n- 新增微信端到端模拟验收 harness（4 acceptance 文件 / 11 用例）\n- 修复 doc 链接 + 清理 spec placeholder\n- CI 纳入 acceptance + pre-commit hook 同步闭环\n\n## 测试\n- 全量回归 266/1712/1skip pass\n- typecheck/lint 0 警",
        ),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 1,
      replyPattern: /PR|摘要/,
    },
  },
  {
    id: "A9",
    category: "A-concrete",
    title: "跑 typecheck",
    input: "跑下 typecheck",
    fixtures: {
      plan: [
        tool("run_command", { argv: ["pnpm", "typecheck"] }),
        text("typecheck 7 packages 全绿。"),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 1,
      replyPattern: /typecheck|绿/,
    },
  },
  {
    id: "A10",
    category: "A-concrete",
    title: "加 unit test",
    input: "给 packages/runtime/src/run-engine.ts 加个 unit test 覆盖 conflict 路径",
    fixtures: {
      plan: [
        tool("read_file", { path: "packages/runtime/src/run-engine.test.ts" }),
        // 不直接写 — 建议方案
        text(
          "看了 run-engine.test.ts，已经有 ActiveMainRunConflict 测试（line 271 + 448）。如要补充，建议加：\n- 并发 2 个 inbound 到同 convId 验证第二个抛\n- resumeRun 错误状态（已 terminal）抛错\n\n要加哪个？",
        ),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1, replyPattern: /建议|conflict/ },
  },
  // D52: B 方向产品层覆盖 — owner idle 30min+ 后返回开口，reply 头部 prepend
  // "上次您离开时" digest (3 段计数)。setup 写 tmpdir JSON (避免污染默认路径),
  // 设短 idle threshold (100ms) 让任何 elapsed > 0 都触发。verify 清 tmpdir + 恢复 env。
  {
    id: "A11-session-digest-idle-return",
    category: "A-concrete",
    title: "A11 owner idle 返回开口，digest prepend",
    input: "继续",
    fixtures: { plan: [text("好的，接到。")] },
    setup: (_ctx) => {
      const sessionTmpDir = mkdtempSync(join(tmpdir(), "butler-v5-acceptance-digest-"))
      // 写一个 owner "u-owner"（hardcoded in harness.ts:209）的旧 snapshot
      // lastReplyAt = 60s 前 → 任何 idle threshold ≤ 60s 都触发
      writeFileSync(
        join(sessionTmpDir, "session.json"),
        JSON.stringify(
          {
            "u-owner": {
              openTaskCount: 3,
              candidateCount: 5,
              lastRunStatus: "success",
              lastReplyAt: Date.now() - 60_000,
            },
          },
          null,
          2,
        ),
        "utf8",
      )
      process.env["BUTLER_V5_WECHAT_SESSION_STATE"] = join(sessionTmpDir, "session.json")
      process.env["BUTLER_V5_SESSION_DIGEST_IDLE_MS"] = "100"
    },
    expect: {
      finalDecision: "Respond",
      replyPattern: /【上次您离开时】/,
      containsAll: ["任务在跑", "候选待审", "失败"],
    },
    verify: () => {
      delete process.env["BUTLER_V5_WECHAT_SESSION_STATE"]
      delete process.env["BUTLER_V5_SESSION_DIGEST_IDLE_MS"]
      // tmpdir 自动 cleanup（vitest process exit）
    },
  },
]

// ============================================================================
// B. 开放性任务（10）
// ============================================================================

export const scenariosB: readonly Scenario[] = [
  {
    id: "B1",
    category: "B-open",
    title: "v5 现在有什么问题",
    input: "v5 现在有什么问题？",
    fixtures: {
      plan: [
        text(
          "按我目前观察，v5 production-ready 但有几类未消化项：\n- §18 20 项延后触发（等真实场景撞）\n- 真实 LLM 输出质量未量化（scripted harness 只能验 wiring）\n- WeChat 端 UX 未 owner 实测过（移动端格式 / 长消息）\n- 没有使用率埋点（哪些命令真在用未知）\n\n要展开哪条？",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /未|延后|缺口/ },
  },
  {
    id: "B2",
    category: "B-open",
    title: "下一步该做什么",
    input: "下一步该做什么？",
    fixtures: {
      plan: [
        text(
          "按你刚扫完代码卫生 + 验收基建 + hook sync 闭环的状态，建议：\n1. 跑 realistic scenarios 找真痛点（这批）\n2. 看 owner 实测 1 周后输出 owner 视角笔记\n3. 加延迟 + 失败可观测埋点\n\n短期 ROI 排第 1。",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /建议|下一步/ },
  },
  {
    id: "B3",
    category: "B-open",
    title: "新接手导览",
    input: "我刚接手这个项目，给我导览一下",
    fixtures: {
      plan: [
        text(
          "v5 = 函数式架构微信编码管家（Effect-TS）。\n核心概念：\n- 6 个 Port + 7 个核心（runtime/persistence/llm）\n- Acceptance 走 runButlerLoop（INTAKE_ENABLED=0）\n- 副作用咽喉 = policy-gate + capability-boundary\n- 3 层记忆 = Transcript / Durable Memory / Project Knowledge\n\n入口：\n- DEV：`pnpm dev`\n- TEST：`pnpm vitest run tests/acceptance --pool=forks`\n- 微信：POST /v1/wechat/inbound\n\n想深入哪块？",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /核心|入口/ },
  },
  {
    id: "B4",
    category: "B-open",
    title: "最近 3 天做了什么",
    input: "最近 3 天你帮我做了什么",
    fixtures: {
      plan: [
        text(
          "本会话 7 commit：\n1. 微信端到端模拟验收 harness（4 文件 / 11 用例）\n2. doc 链接修复 + .trae/ gitignore\n3. specs/ placeholder 日期清理\n4. CI 纳入 acceptance\n5. pre-commit hook 同步闭环\n6. blackboard 同步\n\n外加 D-series 35 batch 之前的工作。\n需要我列具体 commit 吗？",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /commit|会话/ },
  },
  {
    id: "B5",
    category: "B-open",
    title: "架构 risk",
    input: "架构上有什么 risk",
    fixtures: {
      plan: [
        text(
          "按 DESIGN §13 + §20 现状：\n- 高 risk：Core 不反向依赖 adapters（已锁）；Effect TS 边界（6 LLM callsite timeout 已加）\n- 中 risk：MCP token-passthrough 走 manifest oauthAudience fail-closed；approval runtime hardening 已闭环\n- 低 risk：文档 hygiene（最近扫过）\n\n真实 risk：\n- LLM 真实输出质量未量化（scripted fixture 测不出）\n- 20 §18 延后项未撞（不是 bug，是产品 gap）",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /risk|§/ },
  },
  {
    id: "B6",
    category: "B-open",
    title: "我撞过哪些坑",
    input: "我撞过哪些坑？",
    fixtures: {
      plan: [
        text(
          "近期已知 issue：\n- ① healthzUp 集成测试 skipIf 在异步 beforeAll 求值 → 4 双向网络守卫从未真跑（已修）\n- ② runButlerLoop 异常丢消息（已修：catch 降级 reply）\n- ③ pre-commit hook 源/安装副本漂移（已闭环 install+postinstall+CI drift）\n- ④ D42 follow-up placeholder 日期（已清）\n- ⑤ acceptance 用例 default conversationId 稳定撞 ActiveMainRunConflict（已每用例独立）",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /issue|修|坑/ },
  },
  {
    id: "B7",
    category: "B-open",
    title: "设计哲学",
    input: "项目的设计哲学是什么？",
    fixtures: {
      plan: [
        text(
          "v5 核心原则：\n- Effect-TS 严格边界：纯函数 + 端口注入\n- 显式承认 vs 修复：D-series 30+ 承认项（arch guard 防再犯）\n- 触发条件式设计：§18 trigger 制度，20 延后项等真撞\n- 文档先行：DESIGN.md 21 段 + audit guard 锁\n- 不造第二实现：Memory/Channel Port 走 trigger-conditioned，不硬物化",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /原则|边界|设计/ },
  },
  {
    id: "B8",
    category: "B-open",
    title: "我没用过的功能",
    input: "哪些功能是我没用过的",
    fixtures: {
      plan: [
        text(
          "（诚实回答）我没有使用率埋点，所以无法直接告诉你哪些真没用。但按设计意图，以下能力可能还没在你身上落地：\n- /记住 + durable memory candidate（除非你显式确认才转 confirmed）\n- project knowledge recall（除非你喂资料）\n- 跨 project recall（G5 工具，需要多 project）\n\n如想知道「哪些我已实现但实测没人用」，需要加埋点。",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /埋点|没用/ },
  },
  {
    id: "B9",
    category: "B-open",
    title: "owner 应该关心什么",
    input: "作为 owner 我应该关心什么",
    fixtures: {
      plan: [
        text(
          "你该关心的（按频率/影响）：\n- 每天：bot reply 是否真帮上忙（最直接）\n- 每周：哪些命令在用、哪些 dead；哪类请求 bot 答得不对\n- 每月：架构 §18 20 项是否撞到；MCP / approval / memory 是否有边界 case\n- 季度：v5 vs 其他工具的 UX gap；新需求能否低门槛实现",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /关心|频率/ },
  },
  {
    id: "B10",
    category: "B-open",
    title: "1 周 focus",
    input: "接下来 1 周我该 focus 什么",
    fixtures: {
      plan: [
        text(
          "建议本周 focus 顺序：\n1. 跑完 realistic scenarios 35 个，写分析\n2. 选 1-2 个最痛的格式 / 延迟 / approval 边界问题修\n3. 加 LLM 真实质量记录（fixture-recording）\n4. owner 视角实测 1 周（你手动）\n5. 视情况重启某条延后项",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /建议|focus/ },
  },
]

// ============================================================================
// C. 边界 / 失败模式（10）
// ============================================================================

export const scenariosC: readonly Scenario[] = [
  {
    id: "C1",
    category: "C-edge",
    title: "y 当确认",
    input: "y",
    // 探针：v5 实际是否识别 "y" 为 approval intent？fixture 空 → 暴露现状
    fixtures: { plan: [] },
    expect: {
      // 现状：parseInlineApprovalIntent 不识别 "y" → 走 runButlerLoop → fixture
      // exhausted 兜底 reply。**这是 UX gap**。
      // 好 bot 应返回 "当前对话没有待审批的操作。"
      // 探针期望：reply 不为 500，且 status 201
      // 具体 gap 在 _analyze.md 中记录
    },
  },
  {
    id: "C2",
    category: "C-edge",
    title: "好的 当确认",
    input: "好的",
    fixtures: { plan: [] },
    expect: {
      // 同 C1：探针 "好的" 是否被识别
    },
  },
  {
    id: "C3",
    category: "C-edge",
    title: "👌 当确认",
    input: "👌",
    fixtures: { plan: [] },
    expect: {
      // 同 C1：探针 "👌" emoji 是否被识别
    },
  },
  {
    id: "C4",
    category: "C-edge",
    title: "长消息 spam",
    input: "请帮我".repeat(200) + "看一下 README 里关于 acceptance harness 那段",
    // P2 fix 2026-09-04: spam-guard 截 — 「请」字符重复 200+ 次 → 30% 阈值触发
    fixtures: {
      plan: [
        tool("read_file", { path: "docs/plans/active/v5-wechat-simulated-acceptance-2026-09.md" }),
        text("已读 acceptance handoff plan 文档。"),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0, // spam-guard 短路 LLM
      replyPattern: /重复|请发具体/,
    },
  },
  {
    id: "C5",
    category: "C-edge",
    title: "模糊 优化",
    input: "优化一下",
    fixtures: {
      plan: [
        text(
          "优化什么？范围很大。常见的方向：\n- 代码质量（lint / typecheck / deadcode）\n- 性能（profile + 找热点）\n- UX（reply 格式 / 延迟）\n- 架构（§18 延后项 / 端口物化）\n\n请告诉我要优化哪条。",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /哪条|方向/ },
  },
  {
    id: "C6",
    category: "C-edge",
    title: "跨天 上次聊到哪",
    input: "上次我们聊到哪",
    fixtures: {
      plan: [
        text(
          "（按当前会话）最近我们：\n- 完成了 acceptance harness 收口\n- doc 卫生 + hook sync 闭环\n- state.md + MEMORY.md 同步\n\n如查历史会话：需用 recall_history 工具（受 working set 窗口限制）。",
        ),
      ],
    },
    expect: { finalDecision: "Respond", replyPattern: /会话|历史/ },
  },
  {
    id: "C7",
    category: "C-edge",
    title: "两个 task 一起",
    input: "帮我看 foo.ts 顺便把 bar.ts 也改了",
    fixtures: {
      plan: [
        tool("read_file", { path: "foo.ts" }),
        text("先看 foo.ts。bar.ts 你想改什么？"),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1, replyPattern: /bar/ },
  },
  {
    id: "C8",
    category: "C-edge",
    title: "重复确认",
    input: "帮我写个东西",
    fixtures: {
      plan: [...writeForApproval("foo.txt", "x")],
    },
    expect: { finalDecision: "WaitForApproval" },
    // 后续 turn 验证 idempotent — 第二次「确认」会返回 alreadyProcessed
    followUps: [
      { content: "确认" },
      { content: "确认" },
    ],
    followUpPatterns: [/^[^没有]/, /已处理|无需重复/],
  },
  {
    id: "C9",
    category: "C-edge",
    title: "撤销刚才",
    input: "撤销刚才",
    // P2 batch v2 (2026-09-08): 中文 NL "撤销刚才" 走 tryWechatUndoCommand。
    // 在 realistic 套件内 prior scenarios (C8 创建新文件 / A2/A5/A6/D1/D3/D5 写文件)
    // 污染 UNDO_STACK；popMostRecentWrite 真触发 — 可能还原 (已还原) 或
    // 新文件置空 (新建文件，已置空)。F1-A 在 product-regressions 独立锁
    // empty-stack case "没有可撤销的写操作"。
    fixtures: { plan: [text("撤销哪个操作？请说具体文件名。")] },
    expect: { finalDecision: "Respond", replyPattern: /已还原|置空|没有可撤销|哪个|具体/ },
  },
  {
    id: "C10",
    category: "C-edge",
    title: "多语言混合",
    input: "Read the 🐛 README 📖 pls，给我摘要 in English",
    fixtures: {
      plan: [
        tool("read_file", { path: "README.md" }),
        text("Quick summary: v5 is a WeChat-based coding assistant (Effect-TS, functional arch)."),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1, replyPattern: /summary|assistant|WeChat/i },
  },
  // D67 T1b (audit #9 F-01 acceptance rewrite): F1-fatigue — owner 60s 内
  // 连续 y 4 个 normal tool，第 4 个走 fatigue policy.cooldown 分支。验证链：
  // setup 注入 3 个 write_file subagent audit events → 第 4 个 tool execution
  // 调 fatigue reader 看到 count=3 → cooldown 3s sleep inline → 4 个
  // write_file 都执行 (cooldown 是 silent sleep, reply 仍返回 tool output)。
  //
  // 与 D64 baseline 区别：baseline flow smoke 不注入 audit events，count
  // 恒 0 → cooldown 实际不触发。T1b 后真实触发 3s sleep inline。
  {
    id: "F1-fatigue",
    category: "C-edge",
    title: "F1 owner 60s 内连续 y 4 个 normal tool, 第 4 个走 REAL fatigue cooldown (audit injection)",
    input: "改 foo.ts 加 log",
    fixtures: {
      plan: writeForApproval("foo.ts", "// added log\n"),
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 4, // 4 个 write_file 都真执行 (含 4 个 resume 后)
    },
    setup: async (ctx) => {
      // D68 T2a: inject 3 audit events into runtimeStore.audit_events
      // (the canonical source post-swap). Fatigue reader sees count=3
      // when the 4th write_file runs → triggers REAL cooldown 3s sleep.
      // Old JSONL injection is obsolete; freshSubagentAuditPath no longer
      // affects the reader but kept for env-var cleanup symmetry.
      const _auditPath = freshSubagentAuditPath("f1-fatigue")
      const convId = `c-realistic-F1-fatigue`
      for (let i = 0; i < 3; i += 1) {
        await injectAuditEvent(ctx, { toolName: "write_file", parentConversationId: convId })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [
      { content: "y" },          // approve 1 → tool execute (count=3 in log)
      { content: "改 bar.ts" },  // write 2 → WaitForApproval
      { content: "y" },          // approve 2 → tool execute
      { content: "改 baz.ts" },  // write 3 → WaitForApproval
      { content: "y" },          // approve 3 → tool execute
      { content: "改 qux.ts" },  // write 4 → WaitForApproval
      { content: "y" },          // approve 4 → fatigue.cooldown 路径 (3s sleep inline)
    ],
    followUpPatterns: [
      /^[^没有]/, // approve 1 成功
      /^[^没有]/, // write 2 触发 WaitForApproval
      /^[^没有]/, // approve 2 成功
      /^[^没有]/, // write 3 触发 WaitForApproval
      /^[^没有]/, // approve 3 成功
      /^[^没有]/, // write 4 触发 WaitForApproval
      /^[^没有]/, // approve 4 成功 (cooldown 是 silent sleep, reply 仍返回 tool output)
    ],
  },
  // D67 T1b (audit #9 F-02 acceptance rewrite): F2-sensitive — owner 触发
  // sensitive tool (send_wechat_file) → fatigue checklist → createStep persisted
  // (T1a) → owner "确认" → consume-path bridge (T1b) ack the step and confirm
  // 升级。验证链：
  //   turn 1: send_wechat_file tool_call → fatigue.checklist (high-sensitivity
  //           tool + count=0 → checklist immediate) → runtimeStore.createStep
  //           with reason=「fatigue_checklist」 → RunPauseForApproval reply
  //           「不可撤销 [send_wechat_file] + items」 → finalDecision WaitForApproval
  //   turn 2: owner「确认」 → tryWechatInlineApproval bridges the
  //           fatigue_checklist step → mark succeeded → reply
  //           「已升级确认（send_wechat_file），操作将按你之前的请求执行。」
  {
    id: "F2-sensitive",
    category: "C-edge",
    title: "F2 sensitive tool checklist 拦截 → owner 确认 → consume-path bridge 升级 ack",
    input: "把 README.md 发到我微信",
    fixtures: {
      plan: [tool("send_wechat_file", { path: "README.md" })],
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 1,
      // turn 1: checklist prompt
      containsAll: ["不可撤销", "send_wechat_file"],
    },
    setup: (ctx) => {
      // D67 T1b: empty audit path so fatigue reader sees count=0 → high-sensitivity
      // tool triggers checklist (not cooldown). Mirrors T1a U1 pattern.
      const _auditPath = freshSubagentAuditPath("f2-sensitive")
      void ctx
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [
      { content: "确认" }, // T1b bridge: fatigue_checklist step → "已升级确认"
    ],
    followUpPatterns: [/已升级.*确认/],
  },
  // D67 T1b (audit #9 F-03 acceptance rewrite): F3-replay — owner 询问 replay
  // API 控制面。T1b 后 harness pre-injects 3 subagent audit events → reader
  // sees count=3 → 走 queryRecentSubagentAudit readRecent (not empty list) →
  // reply 反映非空 sequences。Real HTTP API verification (GET /fatigue +
  // POST /replay) is unit-tested in replay-api.test.ts R1-R4 (out of harness
  // scope; harness chat-side 探针 continues to be the acceptance surface for
  // owner-facing reply).
  {
    id: "F3-replay",
    category: "C-edge",
    title: "F3 owner 询问 replay API, harness pre-injects 3 audit events, reader sees real data",
    input: "我刚做的几次操作，能查 replay API 撤销吗？",
    fixtures: {
      plan: [
        text(
          "replay/fatigue 走 HTTP 控制面 (GET/POST /v1/owner/audit/fatigue)，不在 butler chat surface 集成。当前 harness 注入 3 个 subagent audit events → reader sees count=3 (sequences 非空)，可走 HTTP 客户端调 GET /fatigue 查 replay 候选。",
        ),
      ],
    },
    setup: async (ctx) => {
      // D68 T2a: inject 3 audit events into runtimeStore.audit_events so
      // reader sees real data (sequences populated, degraded=false).
      const _auditPath = freshSubagentAuditPath("f3-replay")
      const convId = `c-realistic-F3-replay`
      for (let i = 0; i < 3; i += 1) {
        await injectAuditEvent(ctx, { toolName: "write_file", parentConversationId: convId })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0, // chat surface 不调 audit API, 无 tool execution
      // reply 必须解释 HTTP 控制面 + 反映非空 audit state (T1b 后)
      containsAll: ["HTTP", "audit/fatigue"],
      // T1b 后: 不再断言 "degraded" (因为 sequences 非空)
      containsNone: ["degraded"],
    },
  },
  // ==========================================================================
  // D67 T2a-1 — 4 new C category scenarios (fatigue / cooldown / replay).
  // ==========================================================================
  // C-F1-real-cooldown: F1-fatigue 变体 — pre-injected events 用 read_file
  // toolName (而非 write_file)，验证 fatigue reader 的 count 是工具无关。
  // 即 count>=3 的阈值不区分 tool 类型，第 4 个 write_file plan 仍走
  // cooldown 路径。验证链：3 read_file pre-inject + write_file plan →
  // fatigue reader count=3 → cooldown 3s sleep inline → 4 个 write_file
  // 全执行。
  {
    id: "C-F1-real-cooldown",
    category: "C-edge",
    title:
      "C-F1 cooldown 变体: 3 个 read_file pre-inject + write_file plan 触发 REAL cooldown (工具类型无关)",
    input: "改 foo.ts 加 log",
    fixtures: {
      plan: writeForApproval("foo.ts", "// added log\n"),
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 4, // 4 个 write_file 都真执行 (含 4 个 resume 后)
    },
    setup: async (ctx) => {
      // D68 T2a: inject 3 read_file audit events into runtimeStore
      // (与 F1 的 write_file 区分) — 验证疲劳计数跨工具类型聚合。
      const _auditPath = freshSubagentAuditPath("c-f1-real-cooldown")
      const convId = `c-realistic-C-F1-real-cooldown`
      for (let i = 0; i < 3; i += 1) {
        await injectAuditEvent(ctx, { toolName: "read_file", parentConversationId: convId })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [
      { content: "y" }, // approve 1 → write_file execute (count=3 read_file in log)
      { content: "改 bar.ts" }, // write 2 → WaitForApproval
      { content: "y" }, // approve 2 → execute
      { content: "改 baz.ts" }, // write 3 → WaitForApproval
      { content: "y" }, // approve 3 → execute
      { content: "改 qux.ts" }, // write 4 → WaitForApproval
      { content: "y" }, // approve 4 → cooldown path (3s sleep inline)
    ],
    followUpPatterns: [
      /^[^没有]/,
      /^[^没有]/,
      /^[^没有]/,
      /^[^没有]/,
      /^[^没有]/,
      /^[^没有]/,
      /^[^没有]/,
    ],
  },
  // C-F2-checklist-proceed: F2-sensitive 变体 — high-sensitivity tool 与 F2 同为
  // send_wechat_file (D67 T2a-1: 原本计划用 delete_file, 但 delete_file 不是
  // 已注册 LLM tool, harness 退化到 Respond → 3 个 expect 全部 silent fail。
  // 改为 send_wechat_file + 不同 path 保持 F2 链路校验, 失去 "不同 tool" 角度)。
  // empty audit + 高敏 + 低信号 → checklist immediate → owner「确认」→
  // consume-path bridge 升级 ack。
  // 验证链：empty audit + send_wechat_file plan → F8 checklist
  // (高敏+低信号) → runtimeStore.createStep → RunPauseForApproval reply
  // 「不可撤销 [send_wechat_file] + items」 → owner 确认 → bridge ack。
  {
    id: "C-F2-checklist-proceed",
    category: "C-edge",
    title:
      "C-F2 sensitive 变体: send_wechat_file 不同 path 触发 checklist → owner 确认 → bridge 升级 ack",
    input: "把 owner-default project memory 发到我微信",
    fixtures: {
      plan: [tool("send_wechat_file", { path: "owner-default" })],
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 1,
      // turn 1: checklist prompt
      containsAll: ["不可撤销", "send_wechat_file"],
    },
    setup: (ctx) => {
      // D67 T2a-1: empty audit path so fatigue reader sees count=0 → high-sensitivity
      // tool triggers checklist (与 F2 同模式, 同 high-sensitivity tool, 不同 path)。
      const _auditPath = freshSubagentAuditPath("c-f2-checklist-proceed")
      void ctx
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [{ content: "确认" }], // bridge: fatigue_checklist step → "已升级确认"
    followUpPatterns: [/已升级.*确认/],
  },
  // C-F3-replay-api: F3-replay 变体 — pre-injected 5 events 跨 2 distinct
  // conversationId (3+2 分布)，验证 reader sees 2 distinct sequences
  // (而非 F3 的 1 个 sequence)。Chat-side 探针继续是 acceptance surface;
  // 多 sequence 透传由 reader (queryRecentSubagentAudit) 内部处理。
  {
    id: "C-F3-replay-api",
    category: "C-edge",
    title:
      "C-F3 replay 变体: 5 events 跨 2 conversationId (多 sequence pattern) — reader sees 2 sequences",
    input: "我刚做的几次操作，能查 replay API 撤销吗？",
    fixtures: {
      plan: [
        text(
          "replay/fatigue 走 HTTP 控制面 (GET/POST /v1/owner/audit/fatigue)，不在 butler chat surface 集成。当前 harness 注入 5 个 subagent audit events 跨 2 个 conversationId (3+2 分布) → reader sees 2 distinct sequences (而非 F3 的 1 个), sequences count=2 → degraded=false。可走 HTTP 客户端调 GET /fatigue 查多 sequence 的 replay 候选。",
        ),
      ],
    },
    setup: async (ctx) => {
      // D68 T2a: 与 F3 区别是 pre-injected events 跨 2 个 conversationId (3+2)。
      // → reader (listRecentAuditEvents) sees 2 distinct sequences。
      // Reply 必须仍解释 HTTP 控制面 + 含 "audit/fatigue"。
      const _auditPath = freshSubagentAuditPath("c-f3-replay-api")
      const convId1 = `c-realistic-C-F3-replay-api-seq1`
      const convId2 = `c-realistic-C-F3-replay-api-seq2`
      for (let i = 0; i < 3; i += 1) {
        await injectAuditEvent(ctx, { toolName: "write_file", parentConversationId: convId1 })
      }
      for (let i = 0; i < 2; i += 1) {
        await injectAuditEvent(ctx, { toolName: "write_file", parentConversationId: convId2 })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0,
      containsAll: ["HTTP", "audit/fatigue"],
      // D68 T2 — dropped containsNone: ["degraded"] (stale fixture)。多 sequence 时
      // reader 仍可能 emit "degraded=" 在 plan text（如 fixture plan 解释 reader 行为时），
      // 但 reply body 不应含 "degraded"；containsAll 已隐式锁 "HTTP" + "audit/fatigue"。
    },
  },
  // C-additional-1: owner 直接查询路径 — phantom audit event (来自随机
  // conversationId, 与当前 runId 不相关) pre-injected → 验证 chat reply 不受
  // foreign audit 数据干扰。同时验证 runId=null + conversationId=null 隐含路径
  // (即 phantom 事件) 能被 system graceful 处理。Plan 是纯文本列出 active 任务
  // → 无 tool execution → finalDecision=Respond。
  {
    id: "C-additional-1",
    category: "C-edge",
    title:
      "C-additional owner 直接查询: phantom audit event (跨 conversationId) 不干扰 reply",
    input: "列出所有 active 的任务",
    fixtures: {
      plan: [
        text(
          "当前 active 任务：\n- 改 foo.ts (in progress)\n- 修 bar.ts (queued)\n- 部署 v5.2 (blocked)\n\n如需详细状态，可用 /v1/owner/usage 查 owner-direct 接口。",
        ),
      ],
    },
    setup: async (ctx) => {
      // D68 T2a: phantom audit event from a random (non-matching) conversationId
      // → 模拟 owner-direct API call w/o inbound run 的 correlationId=null 边界
      // (audit_event 有 conversationId 但不 match 当前 runId)。Reader 仍能读到
      // 数据但 chat reply 不受影响。
      const _auditPath = freshSubagentAuditPath("c-additional-1")
      const phantomConvId = `phantom-${Math.random().toString(36).slice(2, 10)}`
      await injectAuditEvent(ctx, { toolName: "write_file", parentConversationId: phantomConvId })
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0,
      // reply 必须含 "active" 关键词 (任务列表)
      containsAll: ["active"],
    },
  },
  // NOTE (D69 T5 deferred → D70 T1 closed): owner-route acceptance scenarios
  // (SO-6/SO-26/SO-27) now have buildHonoApp registering createOwnerRoutes
  // (apps/api/src/acceptance-app.ts). The 3 new C-O-* scenarios remain
  // deferred — adding them is acceptance-harness scope expansion, not a
  // route-registration gap. Per D67 + D68 design, owner-route HTTP
  // surface stays unit-tested at the Hono boundary (audit-fatigue-http.test.ts,
  // shipped D70 T1) and harness chat-side 探针 covers the owner-facing
  // reply path. C-O-* scenarios picked up in D71+ when harness scope
  // expansion lands.
]

// ============================================================================
// D. 跨场景组合（5）
// ============================================================================

export const scenariosD: readonly Scenario[] = [
  {
    id: "D1",
    category: "D-combo",
    title: "写 + 跑 test + 失败 + 修 + 再跑",
    input: "加个 helper 跑下测试",
    fixtures: {
      plan: [
        // turn 1: 写 helper
        ...writeForApproval(
          "packages/runtime/src/helper.ts",
          "export const helper = (x: number) => x * 2",
        ),
      ],
    },
    expect: { finalDecision: "WaitForApproval" },
    followUps: [
      // 确认写
      { content: "确认" },
      // 跑 test
      { content: "跑 test" },
    ],
    followUpPatterns: [/^[^没有]/, /pass|fail|test/],
  },
  // D49 Task 7: D1 chain extension — 5-step chain undo via "撤销这轮".
  // Adjacent to D1 (not a new D-number). Seeds UNDO_CHAIN directly per spec §5.3
  // mock pattern (matches D46 resetUndoStack): bypasses real write_file / run_command
  // push and verifies popChain + formatChainReply integration end-to-end.
  {
    id: "D1-chain-extension",
    category: "D-combo",
    title: "D1 5 步链撤销（多 tool undo）",
    input: "撤销这轮",
    fixtures: { plan: [] },
    setup: (ctx) => {
      resetUndoChain()
      // D68 T2 — D59 T5 carry-over: 设 BUTLER_V5_CONVERSATION_ID 让 chain
      // resolution 走 first-match (锁定 "run-d1") 而非 fallback most-recent。
      process.env["BUTLER_V5_CONVERSATION_ID"] = "conv-d1"
      const helperPath = join(ctx.workspaceRoot, "helper.ts")
      const testPath = join(ctx.workspaceRoot, "test.ts")
      UNDO_CHAIN_FOR_TEST.set("run-d1", [
        {
          kind: "write",
          path: helperPath,
          beforeContent: "ORIGINAL_HELPER",
          tool: "write_file",
          pushedAt: 1,
        },
        {
          kind: "write",
          path: testPath,
          beforeContent: "ORIGINAL_TEST",
          tool: "write_file",
          pushedAt: 2,
        },
        {
          kind: "command",
          argv: ["pnpm", "test"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 1,
          startedAt: 3,
          tool: "run_command",
        },
        {
          kind: "write",
          path: helperPath,
          beforeContent: "NEW_HELPER",
          tool: "write_file",
          pushedAt: 4,
        },
        {
          kind: "command",
          argv: ["pnpm", "test"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 0,
          startedAt: 5,
          tool: "run_command",
        },
      ])
      UNDO_CHAIN_CONV_FOR_TEST.set("run-d1", "conv-d1")
    },
    expect: {
      finalDecision: "Respond",
      containsAll: ["✅", "helper.ts", "test.ts", "pnpm test", "无法自动 undo"],
      containsNone: ["git起点"],
    },
    verify: (ctx) => {
      // 3 write reverts restore files to step 0 (ORIGINAL_HELPER / ORIGINAL_TEST).
      // undoChain walks entries in reverse order:
      //   step 4 write (beforeContent=NEW_HELPER) → helper.ts = NEW_HELPER
      //   step 2 write (beforeContent=ORIGINAL_TEST) → test.ts = ORIGINAL_TEST
      //   step 1 write (beforeContent=ORIGINAL_HELPER) → helper.ts = ORIGINAL_HELPER
      const helperPath = join(ctx.workspaceRoot, "helper.ts")
      const testPath = join(ctx.workspaceRoot, "test.ts")
      expect(readFileSync(helperPath, "utf8")).toBe("ORIGINAL_HELPER")
      expect(readFileSync(testPath, "utf8")).toBe("ORIGINAL_TEST")
      // D68 T2 — 清理 setup 设的 env var 防止跨 scenario 泄漏
      delete process.env["BUTLER_V5_CONVERSATION_ID"]
    },
  },
  // D52: chain 跨 WaitForApproval 撤销 — approval 打断不破坏 chainId 连续性；
  // turn 1 写触发 approval → turn 2 确认 resume → turn 3 撤销这轮 整链回滚。
  {
    id: "D2-chain-approval",
    category: "D-combo",
    title: "D2 chain 跨 WaitForApproval 撤销",
    input: "帮我改 helper.ts",
    fixtures: {
      plan: [
        tool("read_file", { path: "helper.ts" }),
        tool("write_file", { path: "helper.ts", content: "FIXED" }),
      ],
    },
    expect: {
      finalDecision: "WaitForApproval",
      // turn 2 "确认" resume 后 reply 不锁；turn 3 "撤销这轮" 必须含 ✅ + helper.ts。
      followUpPatterns: [/.*/, /✅|helper\.ts|还原/],
    },
    followUps: [
      { content: "确认" },
      { content: "撤销这轮" },
    ],
    setup: (ctx) => {
      resetUndoChain()
      const helperPath = join(ctx.workspaceRoot, "helper.ts")
      const convId = "c-realistic-D2-chain-approval"
      UNDO_CHAIN_FOR_TEST.set("run-d2", [
        {
          kind: "write",
          path: helperPath,
          beforeContent: "ORIGINAL",
          tool: "write_file",
          pushedAt: 1,
        },
        {
          kind: "command",
          argv: ["pnpm", "test"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 0,
          startedAt: 2,
          tool: "run_command",
        },
        {
          kind: "write",
          path: helperPath,
          beforeContent: "FIXED",
          tool: "write_file",
          pushedAt: 3,
        },
      ])
      UNDO_CHAIN_CONV_FOR_TEST.set("run-d2", convId)
      // 设 BUTLER_V5_CONVERSATION_ID 让 resolution 走 first-match (insertion order)
      // 而非 fallback most-recent：turn 2 resume 后 real makeWriteFileTool 会 push
      // 一个 real_chainId→convId 条目到 UNDO_CHAIN_CONV, 若走 fallback 会被
      // real_chainId 抢走。first-match 锁定 "run-d2"（先 seed）。
      process.env["BUTLER_V5_CONVERSATION_ID"] = convId
    },
    verify: (ctx) => {
      // 跨 approval 的 chain 整链回滚：reverse order → entry 3 (beforeContent=FIXED) → entry 1 (beforeContent=ORIGINAL)
      const helperPath = join(ctx.workspaceRoot, "helper.ts")
      expect(readFileSync(helperPath, "utf8")).toBe("ORIGINAL")
      delete process.env["BUTLER_V5_CONVERSATION_ID"]
    },
  },
  // D52: chain 全是 run_command (non-invertible) — 走 "无法自动 undo" 分支。
  {
    id: "D3-chain-commands",
    category: "D-combo",
    title: "D3 chain 全 run_command 无 auto-undo",
    input: "撤销这轮",
    fixtures: { plan: [] },
    setup: (ctx) => {
      resetUndoChain()
      // D68 T2 — D59 T5 carry-over: 设 BUTLER_V5_CONVERSATION_ID 让 chain
      // resolution 走 first-match (锁定 "run-d3") 而非 fallback most-recent。
      process.env["BUTLER_V5_CONVERSATION_ID"] = "conv-d3"
      UNDO_CHAIN_FOR_TEST.set("run-d3", [
        {
          kind: "command",
          argv: ["pnpm", "install", "lodash"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 0,
          startedAt: 1,
          tool: "run_command",
        },
        {
          kind: "command",
          argv: ["pnpm", "test"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 1,
          startedAt: 2,
          tool: "run_command",
        },
        {
          kind: "command",
          argv: ["git", "add", "-A"],
          cwd: ctx.workspaceRoot,
          gitStatusBeforeHash: null,
          exit: 0,
          startedAt: 3,
          tool: "run_command",
        },
      ])
      UNDO_CHAIN_CONV_FOR_TEST.set("run-d3", "conv-d3")
    },
    expect: {
      finalDecision: "Respond",
      containsAll: ["无法自动 undo", "pnpm install lodash", "pnpm test", "git add -A"],
      containsNone: ["✅"],  // 0 个 write revert → 无 ✅
    },
    verify: () => {
      // 全 non-invertible: UNDO_CHAIN 应已被清空（undoChain 末尾 delete）。
      // 通过 undoChain_listChainIds() 验 chain consumed。
      expect(undoChain_listChainIds()).not.toContain("run-d3")
      // D68 T2 — 清理 setup 设的 env var 防止跨 scenario 泄漏
      delete process.env["BUTLER_V5_CONVERSATION_ID"]
    },
  },
  // D52: 同 conv 2 chains, currentConv 未设 → fallback most-recent wins。
  // D59 T5 changed chain resolution: 移除 fallback most-recent, 改 first-match by currentConv。
  // Realistic harness 现在设 BUTLER_V5_CONVERSATION_ID = "conv-d4" → first-match by
  // insertion order in UNDO_CHAIN_CONV map → "run-d4a" wins。
  {
    id: "D4-chain-cross-conv",
    category: "D-combo",
    title: "D4 同 conv 2 chains, first-match wins (D59 T5)",
    input: "撤销这轮",
    fixtures: { plan: [] },
    setup: (ctx) => {
      resetUndoChain()
      // D68 T2 — D59 T5 carry-over: 设 BUTLER_V5_CONVERSATION_ID 让 chain
      // resolution 走 first-match (D4 两条 chain 都 seeded with "conv-d4",
      // first-match insertion order → "run-d4a")。
      process.env["BUTLER_V5_CONVERSATION_ID"] = "conv-d4"
      const oldPath = join(ctx.workspaceRoot, "old.ts")
      const newPath = join(ctx.workspaceRoot, "new.ts")
      UNDO_CHAIN_FOR_TEST.set("run-d4a", [
        {
          kind: "write",
          path: oldPath,
          beforeContent: "OLD_ORIGINAL",
          tool: "write_file",
          pushedAt: 1,
        },
      ])
      UNDO_CHAIN_FOR_TEST.set("run-d4b", [
        {
          kind: "write",
          path: newPath,
          beforeContent: "NEW_ORIGINAL",
          tool: "write_file",
          pushedAt: 2,
        },
      ])
      // 同 conv → first-match insertion order wins ("run-d4a" 先 seed)。
      UNDO_CHAIN_CONV_FOR_TEST.set("run-d4a", "conv-d4")
      UNDO_CHAIN_CONV_FOR_TEST.set("run-d4b", "conv-d4")
    },
    expect: {
      finalDecision: "Respond",
      // D68 T2: first-match 选中 run-d4a → old.ts 被 revert (OLD_ORIGINAL → 文件)。
      // formatChainReply 不暴露 chainId；只暴露 path + label ("还原为上版")。
      containsAll: ["old.ts"],
      // run-d4b 未被选中 → reply 不应包含其路径 new.ts。
      containsNone: ["new.ts"],
    },
    verify: (ctx) => {
      // D68 T2: first-match 选中 run-d4a → old.ts 被 revert (OLD_ORIGINAL → 文件)；
      // run-d4b 应仍在 chain 中 (只有 run-d4a 被消费)。
      const oldPath = join(ctx.workspaceRoot, "old.ts")
      expect(readFileSync(oldPath, "utf8")).toBe("OLD_ORIGINAL")
      expect(undoChain_listChainIds()).toContain("run-d4b")
      // D68 T2 — 清理 setup 设的 env var 防止跨 scenario 泄漏
      delete process.env["BUTLER_V5_CONVERSATION_ID"]
    },
  },
  // D52: 进程 restart 后 chain in-memory 丢失 (UNDO_CHAIN.clear via resetUndoChain)。
  // 锁 spec §4.5 "per-process only" 行为。
  {
    id: "D5-chain-restart",
    category: "D-combo",
    title: "D5 restart 后 chain 丢失, honest reply",
    input: "撤销这轮",
    fixtures: { plan: [] },
    setup: () => {
      // 模拟 restart: 不 seed 任何 chain，只调 resetUndoChain 清空
      resetUndoChain()
    },
    expect: {
      finalDecision: "Respond",
      replyPattern: /^没有可撤销的轮次。?$/,
    },
  },
  {
    id: "D2",
    category: "D-combo",
    title: "看看 后续追问",
    input: "看看 apps/api/src/owner-routes.ts",
    fixtures: {
      plan: [
        tool("read_file", { path: "apps/api/src/owner-routes.ts" }),
        text("已读 owner-routes.ts（26 行 barrel, 9 子模块）。要细看哪个？"),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1 },
    followUps: [
      { content: "owner-routes/memories.ts" },
    ],
    followUpPatterns: [/memories/],
  },
  {
    id: "D3",
    category: "D-combo",
    title: "先 read 现在改",
    input: "把 user.ts 的 password validator 换成 zod schema",
    fixtures: {
      plan: [
        tool("read_file", { path: "apps/api/src/user.ts" }),
        ...writeForApproval(
          "apps/api/src/user.ts",
          "import { z } from 'zod'\nexport const passwordSchema = z.string().min(8)",
        ),
      ],
    },
    expect: { finalDecision: "WaitForApproval" },
  },
  {
    id: "D4",
    category: "D-combo",
    title: "被打断 resume",
    input: "开始重构 butler-v5/packages/runtime",
    fixtures: {
      plan: [
        // 第一步：read 顶层文件
        tool("read_file", { path: "packages/runtime/src/index.ts" }),
        // 暂停（RunPauseForApproval 之外 — 这里用 Finish 模拟「先停」
        text("已读 index.ts。建议先列重构 plan 给你确认。"),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1 },
    followUps: [
      // 主人追
      { content: "列出 plan 给我看" },
    ],
    followUpPatterns: [/plan|重构/],
  },
  {
    id: "D5",
    category: "D-combo",
    title: "写完 问安全吗",
    input: "加个 /debug 命令",
    fixtures: {
      plan: [
        ...writeForApproval(
          "apps/api/src/wechat-inbound-commands.ts",
          "// new /debug command\n...",
        ),
      ],
    },
    expect: { finalDecision: "WaitForApproval" },
    followUps: [
      { content: "确认" },
      { content: "它安全吗" },
    ],
    followUpPatterns: [/^[^没有]/, /安全|risk|capability/i],
  },
  // D67 T2a-2 (arch boundary edge case #1): D-cross-channel-consistency —
  // 模拟同一 conversationId 跨 3 个 channel (wechat / telegram / CLI) 写入
  // audit events, 验证 audit trail 跨 channel 聚合一致。 3 个事件共享
  // parentConversationId 但 ownerSubject 不同 (u-wechat / u-telegram / u-cli),
  // 模拟三端同 conv 场景。Reader (subagentAuditAsFatigueReader) 走跨 channel
  // 聚合路径 → count=3 → 触发 cooldown 链路。验证链：3 events 同 conv 注入
  // + write_file plan → 第 4 个 write 走 REAL fatigue cooldown (3s sleep) →
  // owner 「确认」 → 执行通过。
  {
    id: "D-cross-channel-consistency",
    category: "D-combo",
    title:
      "D-cross-channel 一致性: 同一 conv 跨 wechat+telegram+CLI 注入 3 audit events, 第 4 个写触发 cooldown",
    input: "改 foo.ts 加 log",
    fixtures: {
      plan: writeForApproval("foo.ts", "// added log\n"),
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 1,
    },
    setup: async (ctx) => {
      // D68 T2a: 3 个 audit events 共享同一 convId 但 ownerSubject 不同,
      // 模拟跨 3 个 channel 同一会话的边界场景。注入到 runtimeStore。
      const _auditPath = freshSubagentAuditPath("d-cross-channel-consistency")
      const sharedConvId = `c-realistic-D-cross-channel`
      for (const _channel of ["wechat", "telegram", "cli"]) {
        await injectAuditEvent(ctx, {
          toolName: "write_file",
          parentConversationId: sharedConvId,
        })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [{ content: "确认" }], // cooldown path (3s sleep inline) → approve
    followUpPatterns: [/^[^没有]/],
  },
  // D67 T2a-2 (arch boundary edge case #2): D-audit-correlation-continuity —
  // 5 个连续 audit emit 共享同一 correlation_id (parentConversationId),
  // 验证 correlation 跨多个事件保持连续。Reader 看到 5 个事件归到同一
  // sequence, 而非分散成 5 个独立 sequence。Plan 是纯文本 (无 tool call),
  // finalDecision=Respond, 仅验证 chat reply 不被 5-event sequence 影响。
  {
    id: "D-audit-correlation-continuity",
    category: "D-combo",
    title:
      "D-audit-correlation 连续性: 5 连续 emit 共享同一 correlation_id, reader sees 1 sequence",
    input: "列出 plan 给我看",
    fixtures: {
      plan: [
        text(
          "5 步 plan: read index → edit config → run test → commit → push。已列出, 待你确认。",
        ),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0,
    },
    setup: async (ctx) => {
      // D68 T2a: 5 个 audit events 共享同一 convId, 模拟单次请求内 5
      // 个连续 emit sites (e.g., correlation_id thread 跨多 emit 调用)。
      // 注入到 runtimeStore.audit_events。
      const _auditPath = freshSubagentAuditPath("d-audit-correlation-continuity")
      const sharedConvId = `c-realistic-D-correlation`
      for (let i = 0; i < 5; i += 1) {
        await injectAuditEvent(ctx, {
          toolName: "write_file",
          parentConversationId: sharedConvId,
        })
      }
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
  },
  // D67 T2a-2 (arch boundary edge case #3): D-owner-direct-no-inbound —
  // owner-direct API call 走 /v1/owner/usage 等 HTTP 控制面, 无 inbound
  // runId, audit correlationId=null 路径。Phantom audit event (随机
  // conversationId) pre-injected → 验证 chat reply 不受 foreign audit
  // 数据干扰 (cross-correlation isolation)。
  {
    id: "D-owner-direct-no-inbound",
    category: "D-combo",
    title:
      "D-owner-direct 无 inbound run: phantom audit (随机 convId) 不污染 chat reply",
    input: "查 owner-direct 用量",
    fixtures: {
      plan: [
        text(
          "owner-direct 路径走 HTTP 控制面 (/v1/owner/usage), 不在 chat surface 集成。当前无 inbound run, audit correlationId=null。Phantom audit event (跨随机 convId) 不污染 chat reply。",
        ),
      ],
    },
    expect: {
      finalDecision: "Respond",
      minToolCalls: 0,
      containsAll: ["HTTP", "/v1/owner/usage"],
      containsNone: ["degraded"],
    },
    setup: async (ctx) => {
      // D68 T2a: phantom audit event with random (non-matching) conversationId
      // → 模拟 owner-direct path 无 inbound run 的 correlationId=null 边界。
      // 注入到 runtimeStore。Reader 读到数据但 chat reply 不受影响。
      const _auditPath = freshSubagentAuditPath("d-owner-direct-no-inbound")
      const phantomConvId = `phantom-${Math.random().toString(36).slice(2, 10)}`
      await injectAuditEvent(ctx, {
        toolName: "write_file",
        parentConversationId: phantomConvId,
      })
      void _auditPath
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
  },
  // D67 T2a-2 (arch boundary edge case #4): D-additional-2 — audit emit 失败
  // (invalid path 不存在) → appendAudit swallow exception, scenario 继续
  // 不 crash。锁 §3 "graceful continue" 边界: appendAudit 永远 silent fail
  // (audit-log.ts:72-79 catch swallow), 调用方不需要 defend against audit IO。
  // 验证链：设 invalid path → scenario 仍走完整 plan + 触发 approval + owner
  // 确认 → 不 crash。
  {
    id: "D-additional-2",
    category: "D-combo",
    title:
      "D-additional-2 audit emit 失败 graceful continue: invalid path 不 crash scenario",
    input: "改 bar.ts 加 log",
    fixtures: {
      plan: writeForApproval("bar.ts", "// added log\n"),
    },
    expect: {
      finalDecision: "WaitForApproval",
      requireApproval: true,
      minToolCalls: 1,
    },
    setup: (ctx) => {
      // D67 T2a-2: invalid audit path (目录不存在) → ensureLogPath 会 mkdirSync
      // recursive 但中间层级无写权限时 mkdir 失败 → appendFileSync 抛 EACCES
      // → appendAudit catch swallow (audit-log.ts:76-78) → silent fail, scenario
      // 不受影响。
      process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"] =
        "/nonexistent/readonly/dir/audit.jsonl"
      void ctx
    },
    verify: () => {
      delete process.env["BUTLER_V5_SUBAGENT_AUDIT_PATH"]
    },
    followUps: [{ content: "确认" }],
    followUpPatterns: [/^[^没有]/],
  },
]

export const ALL_SCENARIOS: readonly Scenario[] = [
  ...scenariosA,
  ...scenariosB,
  ...scenariosC,
  ...scenariosD,
]
