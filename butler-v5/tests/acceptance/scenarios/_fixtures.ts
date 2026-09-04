/**
 * 真实 owner 任务场景集 — 用于 product-layer 行为分析。
 *
 * 设计原则：
 * - 每个场景 = `input` + `followUps` + `fixtures`（好 bot 行为）+ `expect`（断言 + 度量）
 * - fixture 是手工编码的"好 bot"应答序列（不是真 LLM，但反映 v5 已实现能力下的合理行为）
 * - 多 turn 时 fixtures 按 LLM 调用顺序消耗；counter 在 setFixtures 时重置
 * - 写文件触发 `WaitForApproval`；owner 后续「确认」走 inline approval
 *
 * 4 类共 35 场景：
 * A. 真实开发任务（具体可执行）— 10
 * B. 开放性任务（探索型）— 10
 * C. 边界 / 失败模式 — 10
 * D. 跨场景组合 — 5
 */
import type { FixtureEntry } from "../harness.js"

export type ScenarioCategory = "A-concrete" | "B-open" | "C-edge" | "D-combo"

export interface ScenarioExpect {
  /** reply 必须 match 的正则或子串（任一即可） */
  readonly replyPattern?: RegExp | string
  /** 期望 finalDecision（first turn） */
  readonly finalDecision?: "Respond" | "WaitForApproval" | "Finish"
  /** 期望至少触发的工具调用数（across all turns） */
  readonly minToolCalls?: number
  /** 是否期望走 approval flow */
  readonly requireApproval?: boolean
  /** 多 turn 场景：第 2+ turn 的 reply match */
  readonly followUpPatterns?: (RegExp | string)[]
}

export interface Scenario {
  readonly id: string
  readonly category: ScenarioCategory
  readonly title: string
  readonly input: string
  /** 后续 turn（含 conversationId 复用） */
  readonly followUps?: readonly { readonly content: string }[]
  readonly fixtures: {
    readonly plan?: readonly FixtureEntry[]
    readonly exec?: readonly FixtureEntry[]
    readonly intake?: readonly FixtureEntry[]
  }
  readonly expect: ScenarioExpect
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
    title: "长消息",
    input: "请帮我".repeat(200) + "看一下 README 里关于 acceptance harness 那段",
    fixtures: {
      plan: [
        tool("read_file", { path: "docs/plans/active/v5-wechat-simulated-acceptance-2026-09.md" }),
        text("已读 acceptance handoff plan 文档。"),
      ],
    },
    expect: { finalDecision: "Respond", minToolCalls: 1, replyPattern: /acceptance/ },
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
    fixtures: { plan: [text("撤销哪个操作？请说具体文件名。")] },
    expect: { finalDecision: "Respond", replyPattern: /哪个|具体/ },
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
  {
    id: "D2",
    category: "D-combo",
    title: "看看 后续追问",
    input: "看看 apps/api/src/owner-routes.ts",
    fixtures: {
      plan: [
        tool("read_file", { path: "apps/api/src/owner-routes.ts" }),
        text("已读 owner-routes.ts（1200+ 行，分 7 子模块）。要细看哪个？"),
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
]

export const ALL_SCENARIOS: readonly Scenario[] = [
  ...scenariosA,
  ...scenariosB,
  ...scenariosC,
  ...scenariosD,
]
