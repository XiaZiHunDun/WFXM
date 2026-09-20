/**
 * 真实 owner 任务场景 — product-layer 行为分析。
 *
 * 跑 41 个场景（11 真实开发 + 10 开放性 + 10 边界 + 10 组合（5 基础 + 5 chain 撤销）），每个场景：
 * - 注入"好 bot"的 fixture 序列
 * - 通过 /v1/wechat/inbound 跑真实 wiring
 * - 断言 reply pattern / final decision / 工具调用数 / approval flow
 * - 收集 metrics（reply 长度 / 工具序列 / approval 数 / final state）→ 写 _analyze.md
 *
 * 关键约束：fixture 是手工"好 bot"行为，不是真 LLM。目的是分析 v5 wrap-around
 * （工具链 / approval / multi-turn / error）是否承载真实场景。
 */
import { describe, expect, it, afterAll, beforeAll } from "vitest"
import { writeFileSync } from "node:fs"
import { join } from "node:path"
import { ALL_SCENARIOS, type ScenarioSetupCtx } from "./_fixtures.js"
import { resetUndoStack } from "@butler/api/workspace-tools.js"
import {
  makeAcceptanceApp,
  sendWechatMessage,
  type AcceptanceApp,
} from "../harness.js"
import { runMultiRound } from "../multi-round.js"

interface TurnMetric {
  readonly input: string
  readonly reply: string
  readonly replyLen: number
  readonly status: number
  readonly finalDecision?: string
  readonly toolCalls?: number
}

interface ScenarioMetric {
  readonly id: string
  readonly category: string
  readonly title: string
  readonly turns: readonly TurnMetric[]
  readonly approvalCount: number
  readonly totalToolCalls: number
  readonly passed: boolean
  readonly notes: string[]
}

describe("acceptance/realistic (41 真实场景产品层行为)", () => {
  let app: AcceptanceApp
  const metrics: ScenarioMetric[] = []

  beforeAll(async () => {
    resetUndoStack()
    app = await makeAcceptanceApp()
  })
  afterAll(async () => {
    await app.close()
    // 写 _analyze.md
    writeFileSync(
      join(import.meta.dirname ?? ".", "_analyze.md"),
      renderAnalyze(metrics),
      "utf8",
    )
  })

  // D53a: 把原 it() 主体（除 state init + metrics.push）抽出，给 runMultiRound N=3 wrap 用。
  // 41 scenario 全走同一 it() + runScenario + runMultiRound 模式 (Task 6 全量 retro)。
  async function runScenario(
    scenario: (typeof ALL_SCENARIOS)[number],
    convId: string,
    ctx: ScenarioSetupCtx,
    notes: string[],
    turns: TurnMetric[],
  ): Promise<{ approvalCount: number; totalToolCalls: number }> {
    let approvalCount = 0
    let totalToolCalls = 0

    // D68 T2a: per-scenario audit_events isolation. The fatigue reader
    // (subagentAuditAsFatigueReader) now queries runtimeStore.audit_events
    // (the canonical source post-swap), so scenarios that pre-inject audit
    // events would leak into subsequent scenarios if we didn't reset.
    // JSONL bridge had implicit per-scenario isolation via fresh tmpdir;
    // runtimeStore shares state across scenarios so we truncate via raw
    // SQL (Drizzle's `deleteFrom` needs a schema-aware table ref, raw
    // `sql\`DELETE FROM ...\`` is the cheapest escape hatch).
    const { sql } = await import("drizzle-orm")
    await ctx.app.db.execute(sql`DELETE FROM audit_events`)

    if (scenario.setup) {
      await scenario.setup(ctx)
    }

    try {
      // turn 1
      app.setFixtures({
        plan: scenario.fixtures.plan ?? [],
        exec: scenario.fixtures.exec ?? [],
        intake: scenario.fixtures.intake ?? [],
      })
      const r1 = await sendWechatMessage(app, {
        content: scenario.input,
        conversationId: convId,
      })
      turns.push({
        input: scenario.input,
        reply: r1.reply ?? "",
        replyLen: (r1.reply ?? "").length,
        status: r1.status,
        finalDecision: r1.finalDecision,
        toolCalls: r1.toolCalls,
      })
      if (r1.finalDecision === "WaitForApproval") approvalCount += 1
      totalToolCalls += r1.toolCalls ?? 0

      // 断言 turn 1
      expect(r1.status).toBe(201)
      if (scenario.expect.finalDecision) {
        expect(r1.finalDecision).toBe(scenario.expect.finalDecision)
      }
      if (scenario.expect.replyPattern) {
        const p = scenario.expect.replyPattern
        const text = r1.reply ?? ""
        const ok = p instanceof RegExp ? p.test(text) : text.includes(p)
        if (!ok) notes.push(`reply 不 match ${p}，实际："${text.slice(0, 80)}..."`)
        expect(ok).toBe(true)
      }
      if (scenario.expect.containsAll) {
        const text = r1.reply ?? ""
        for (const needle of scenario.expect.containsAll) {
          if (!text.includes(needle)) {
            notes.push(`reply 不包含 ${needle}，实际："${text.slice(0, 80)}..."`)
          }
          expect(text).toContain(needle)
        }
      }
      if (scenario.expect.containsNone) {
        const text = r1.reply ?? ""
        for (const needle of scenario.expect.containsNone) {
          if (text.includes(needle)) {
            notes.push(`reply 不应包含 ${needle}，实际："${text.slice(0, 80)}..."`)
          }
          expect(text).not.toContain(needle)
        }
      }
      if (scenario.expect.minToolCalls !== undefined) {
        // 多 turn 累计后再断言
      }
      if (scenario.expect.requireApproval) {
        expect(r1.finalDecision).toBe("WaitForApproval")
      }

      // follow-ups
      for (let i = 0; i < (scenario.followUps ?? []).length; i += 1) {
        const fu = scenario.followUps?.[i]
        if (!fu) continue
        // 重新 setFixtures 一次（counter 重置；模拟"新 LLM 调用"）
        app.setFixtures({
          plan: scenario.fixtures.plan ?? [],
          exec: scenario.fixtures.exec ?? [],
          intake: scenario.fixtures.intake ?? [],
        })
        const rN = await sendWechatMessage(app, {
          content: fu.content,
          conversationId: convId,
        })
        turns.push({
          input: fu.content,
          reply: rN.reply ?? "",
          replyLen: (rN.reply ?? "").length,
          status: rN.status,
          finalDecision: rN.finalDecision,
          toolCalls: rN.toolCalls,
        })
        if (rN.finalDecision === "WaitForApproval") approvalCount += 1
        totalToolCalls += rN.toolCalls ?? 0

        // 断言 follow-up
        const fuPattern = scenario.expect.followUpPatterns?.[i]
        if (fuPattern) {
          const text = rN.reply ?? ""
          const ok = fuPattern instanceof RegExp ? fuPattern.test(text) : text.includes(fuPattern)
          if (!ok) notes.push(`followUp[${i}] 不 match ${fuPattern}，实际："${text.slice(0, 80)}..."`)
          expect(ok).toBe(true)
        }
      }

      // 累计断言
      if (scenario.expect.minToolCalls !== undefined) {
        if (totalToolCalls < scenario.expect.minToolCalls) {
          notes.push(`tool calls ${totalToolCalls} < expected ${scenario.expect.minToolCalls}`)
        }
        expect(totalToolCalls).toBeGreaterThanOrEqual(scenario.expect.minToolCalls)
      }

      return { approvalCount, totalToolCalls }
    } finally {
      // D49: verify 在 finally 中跑，确保即使 turn 断言失败也执行（让 fs 状态可观测）。
      if (scenario.verify) {
        await scenario.verify(ctx)
      }
    }
  }

  for (const scenario of ALL_SCENARIOS) {
    it(`${scenario.id} ${scenario.title} [N=3]`, async () => {
      // D49: 透传 harness workspaceRoot 给 setup/verify 钩子（D1-chain-extension 用）。
      // D67 T1b: 透传 app 给 setup/verify 钩子（F3-replay HTTP API 用）。
      const ctx = { workspaceRoot: app.workspaceRoot, app }
      // D53a Task 6: 3 round 各跑一次, 记录 last round 数据（fixtures 决定性, 3 round 等价）。
      let lastTurns: TurnMetric[] = []
      let lastNotes: string[] = []
      let lastApprovalCount = 0
      let lastTotalToolCalls = 0
      // D68 T2 — per-round convId 隔离 (fixes 8 stale fixtures: A2/A5/A6/F2/C-F2/D3-no-fu/D1/D5)。
      // 此前 3 round 共享同一个 convId → round 2/3 读到 round 1 残留状态。
      let roundNum = 0

      const result = await runMultiRound(
        async () => {
          roundNum += 1
          const convId = `c-realistic-${scenario.id}-r${roundNum}`
          // 每 round fresh state: notes/turns 必须 round-local, 否则 round 1 污染 round 2
          const notes: string[] = []
          const turns: TurnMetric[] = []
          const { approvalCount, totalToolCalls } = await runScenario(
            scenario, convId, ctx, notes, turns,
          )
          // 记录 last round 数据 (per-scenario metrics 而非 per-round, 避免 _analyze.md 3× 重复)
          lastTurns = turns
          lastNotes = notes
          lastApprovalCount = approvalCount
          lastTotalToolCalls = totalToolCalls
        },
        { rounds: 3, aggregation: "all" },
      )

      // D68 T1: harness bug fix — multi-round.ts:78-79 契约要求 caller 读 result.passed
      // (helper 不 throw on aggregation=all failure); 此前 silently push passed=true 是 silent-failure
      expect(result.passed).toBe(true)
      metrics.push({
        id: scenario.id,
        category: scenario.category,
        title: scenario.title,
        turns: lastTurns,
        approvalCount: lastApprovalCount,
        totalToolCalls: lastTotalToolCalls,
        passed: result.passed,
        notes: lastNotes,
      })
    }, 90_000)
  }
})

// ============================================================================
// _analyze.md 渲染
// ============================================================================

function renderAnalyze(metrics: readonly ScenarioMetric[]): string {
  const lines: string[] = []
  lines.push(`# Acceptance Realistic Scenarios — 产品层行为分析`)
  lines.push("")
  // D73 T5 (audit #19 SO-008): use the actual ISO date + scenario count
  // instead of the hardcoded "2026-09-11（41 场景）" stale literal.
  // Pre-T5 the header contradicted the body (52 scenarios in body but
  // "41 场景" in header) — mtime was 2026-09-18. Now self-consistent.
  lines.push(`生成时间：${new Date().toISOString().slice(0, 10)}（${metrics.length} 场景自动跑出）`)
  lines.push("")
  lines.push(`## 总览`)
  lines.push("")
  const total = metrics.length
  const passed = metrics.filter((m) => m.passed).length
  const failed = total - passed
  const totalApprovals = metrics.reduce((s, m) => s + m.approvalCount, 0)
  const totalTools = metrics.reduce((s, m) => s + m.totalToolCalls, 0)
  const totalReplyChars = metrics.reduce(
    (s, m) => s + m.turns.reduce((t, x) => t + x.replyLen, 0),
    0,
  )
  lines.push(`- 场景数：${total}`)
  lines.push(`- 通过：${passed} / 失败：${failed}`)
  lines.push(`- 触发 approval：${totalApprovals} 次`)
  lines.push(`- 工具调用总数：${totalTools}`)
  lines.push(`- reply 字符总数：${totalReplyChars}`)
  lines.push("")
  lines.push(`## 按类别汇总`)
  lines.push("")
  const byCategory = new Map<string, ScenarioMetric[]>()
  for (const m of metrics) {
    if (!byCategory.has(m.category)) byCategory.set(m.category, [])
    byCategory.get(m.category)?.push(m)
  }
  for (const [cat, list] of byCategory) {
    const passCount = list.filter((m) => m.passed).length
    lines.push(`### ${cat}（${list.length} 场景，${passCount} 通过）`)
    lines.push("")
    lines.push(`| ID | 标题 | 工具 | 审批 | 状态 |`)
    lines.push(`|---|---|---|---|---|`)
    for (const m of list) {
      lines.push(
        `| ${m.id} | ${m.title} | ${m.totalToolCalls} | ${m.approvalCount} | ${m.passed ? "✅" : "❌"} |`,
      )
    }
    lines.push("")
  }
  lines.push(`## 每场景 reply 抓取（用于人工 review）`)
  lines.push("")
  for (const m of metrics) {
    lines.push(`### ${m.id} — ${m.title}（${m.category}）`)
    lines.push("")
    for (let i = 0; i < m.turns.length; i += 1) {
      const t = m.turns[i]
      if (!t) continue
      lines.push(`**turn ${i + 1}**`)
      lines.push(``)
      lines.push(`> in: ${t.input.slice(0, 100)}${t.input.length > 100 ? "..." : ""}`)
      lines.push(``)
      lines.push(`< ${t.reply}`)
      lines.push(``)
      lines.push(
        `_decision=${t.finalDecision ?? "-"} | toolCalls=${t.toolCalls ?? 0} | replyLen=${t.replyLen}_`,
      )
      lines.push(``)
    }
    if (m.notes.length > 0) {
      lines.push(`**notes**`)
      for (const n of m.notes) lines.push(`- ${n}`)
      lines.push("")
    }
  }
  return lines.join("\n")
}
