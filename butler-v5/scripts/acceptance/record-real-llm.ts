/**
 * 真实 LLM 录音脚本 — owner 跑，捕获 v5 wrap-around 的真 LLM 行为。
 *
 * 用法:
 *   cd butler-v5
 *   MINIMAX_API_KEY=sk-mm-... pnpm tsx scripts/acceptance/record-real-llm.ts
 *
 * 行为:
 *   1. 加载 35 realistic scenarios（_fixtures.ts）
 *   2. 用 production wiring（无 fixture env 触发真 LLM）
 *   3. 每个场景跑 + 收集 reply / finalDecision / toolCalls / 真实 LLM 调用 latency
 *   4. 写到 tests/acceptance/scenarios/recordings/{scenario-id}.json
 *
 * 输出: tests/acceptance/scenarios/recordings/ 目录 + 一份 _summary.md
 *
 * 约束:
 *   - 必须有 MINIMAX_API_KEY（或 MINIMAX_CN_API_KEY）
 *   - 不动 production code（仅调用 harness + 复用模型 router）
 *   - 不动 _fixtures.ts（fixtures 仍作 scripted 模式 baseline）
 *   - recordings 是真 LLM 行为快照，可用作 future fixture 源（当 v5 prompt
 *     升级时跑一遍 diff 检测 regression）
 */
import { writeFileSync, mkdirSync } from "node:fs"
import { join } from "node:path"
import { ALL_SCENARIOS } from "../../tests/acceptance/scenarios/_fixtures.js"
import { makeAcceptanceApp, sendWechatMessage, type AcceptanceApp } from "../../tests/acceptance/harness.js"

const OUT_DIR = join(import.meta.dirname ?? ".", "..", "..", "tests/acceptance/scenarios/recordings")

interface TurnRecord {
  readonly input: string
  readonly reply: string
  readonly replyLen: number
  readonly finalDecision?: string
  readonly toolCalls?: number
  readonly latencyMs: number
}

interface ScenarioRecord {
  readonly id: string
  readonly category: string
  readonly title: string
  readonly input: string
  readonly turns: readonly TurnRecord[]
  readonly recordedAt: string
  readonly model: { readonly plan: string; readonly exec: string }
  readonly apiKeyMask: string // last 4 chars
}

async function main(): Promise<void> {
  // Verify real LLM is reachable
  const apiKey = process.env["MINIMAX_API_KEY"] ?? process.env["MINIMAX_CN_API_KEY"] ?? ""
  if (!apiKey) {
    console.error(
      "[record-real-llm] MINIMAX_API_KEY (or MINIMAX_CN_API_KEY) is required. " +
        "Set one in env to record real LLM behavior.",
    )
    process.exit(1)
  }
  const modelPlan = process.env["BUTLER_V5_MODEL_PLAN"] ?? process.env["MINIMAX_MODEL"] ?? "MiniMax-M3"
  const modelExec = process.env["BUTLER_V5_MODEL_EXEC"] ?? modelPlan

  // CRITICAL: do NOT set BUTLER_V5_LLM_FIXTURE_DIR — we want real LLM.
  // Also, do NOT set BUTLER_V5_INTAKE_ENABLED (default is 1; we set 0 to
  // go through runButlerLoop with full wechat tool set + approval flow).
  process.env["BUTLER_V5_INTAKE_ENABLED"] = "0"
  delete process.env["BUTLER_V5_LLM_FIXTURE_DIR"]

  mkdirSync(OUT_DIR, { recursive: true })
  const app: AcceptanceApp = await makeAcceptanceApp({ noFixture: true })
  const masked = `***${apiKey.slice(-4)}`
  const recordedAt = new Date().toISOString()
  const summary: Array<{ id: string; turns: number; totalLatencyMs: number }> = []

  try {
    for (const scenario of ALL_SCENARIOS) {
      const convId = `c-real-llm-${scenario.id}-${Date.now()}`
      const turns: TurnRecord[] = []
      const totalStart = Date.now()

      // turn 1 (use env without fixtures set — production picks real LLM)
      const t1Start = Date.now()
      const r1 = await sendWechatMessage(app, {
        content: scenario.input,
        conversationId: convId,
      })
      turns.push({
        input: scenario.input,
        reply: r1.reply ?? "",
        replyLen: (r1.reply ?? "").length,
        finalDecision: r1.finalDecision,
        toolCalls: r1.toolCalls,
        latencyMs: Date.now() - t1Start,
      })

      for (const fu of scenario.followUps ?? []) {
        const fuStart = Date.now()
        const rN = await sendWechatMessage(app, {
          content: fu.content,
          conversationId: convId,
        })
        turns.push({
          input: fu.content,
          reply: rN.reply ?? "",
          replyLen: (rN.reply ?? "").length,
          finalDecision: rN.finalDecision,
          toolCalls: rN.toolCalls,
          latencyMs: Date.now() - fuStart,
        })
      }

      const record: ScenarioRecord = {
        id: scenario.id,
        category: scenario.category,
        title: scenario.title,
        input: scenario.input,
        turns,
        recordedAt,
        model: { plan: modelPlan, exec: modelExec },
        apiKeyMask: masked,
      }
      writeFileSync(join(OUT_DIR, `${scenario.id}.json`), JSON.stringify(record, null, 2), "utf8")
      summary.push({
        id: scenario.id,
        turns: turns.length,
        totalLatencyMs: Date.now() - totalStart,
      })
      process.stdout.write(`  ✓ ${scenario.id} (${turns.length} turns, ${turns.reduce((s, t) => s + t.latencyMs, 0)}ms)\n`)
    }
  } finally {
    await app.close()
  }

  // write summary
  const totalMs = summary.reduce((s, x) => s + x.totalLatencyMs, 0)
  const totalTurns = summary.reduce((s, x) => s + x.turns, 0)
  const summaryLines = [
    `# Real LLM Recording — ${recordedAt}`,
    ``,
    `- scenarios: ${summary.length}`,
    `- total turns: ${totalTurns}`,
    `- total latency: ${totalMs}ms (avg ${Math.round(totalMs / summary.length)}ms per scenario)`,
    `- model: plan=${modelPlan} exec=${modelExec}`,
    `- key: ${masked}`,
    ``,
    `## Per-scenario`,
    ``,
    `| ID | Turns | Latency (ms) |`,
    `|---|---|---|`,
    ...summary.map((s) => `| ${s.id} | ${s.turns} | ${s.totalLatencyMs} |`),
  ]
  writeFileSync(join(OUT_DIR, "_summary.md"), summaryLines.join("\n") + "\n", "utf8")
  console.log(`\n[record-real-llm] done: ${summary.length} scenarios, ${totalTurns} turns, ${totalMs}ms total`)
  console.log(`[record-real-llm] recordings in ${OUT_DIR}`)
  console.log(`[record-real-llm] summary: ${join(OUT_DIR, "_summary.md")}`)
}

main().catch((err) => {
  console.error("[record-real-llm] fatal:", err)
  process.exit(1)
})