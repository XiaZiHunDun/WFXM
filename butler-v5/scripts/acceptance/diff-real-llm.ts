/**
 * 真实 LLM recordings vs fixture 期望 diff — rotation policy step 3。
 *
 * 用法:
 *   cd butler-v5
 *   pnpm diff:real-llm                              # diff 当前 recordings/
 *   pnpm diff:real-llm -- --dir <path>              # diff 任意目录
 *   pnpm diff:real-llm -- --dir tests/acceptance/scenarios/recordings-archive/v7-current
 *
 * 输出: markdown 表（aggregate 头 + per-scenario 行）到 stdout。
 * aggregate gate 见 docs/plans/active/v5-real-llm-v8-iteration-2026-09.md §5。
 */
import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { ALL_SCENARIOS } from "../../tests/acceptance/scenarios/_fixtures.js"

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
  readonly turns: readonly TurnRecord[]
  readonly model: { readonly plan: string; readonly exec: string }
}

const DEFAULT_DIR = join(
  import.meta.dirname ?? ".",
  "..",
  "..",
  "tests/acceptance/scenarios/recordings",
)

const parseDir = (argv: readonly string[]): string => {
  const i = argv.indexOf("--dir")
  const value = i >= 0 ? argv[i + 1] : undefined
  if (i >= 0 && (value === undefined || value.startsWith("--"))) {
    throw new Error("--dir requires a path argument")
  }
  return value ?? DEFAULT_DIR
}

const REC_DIR = parseDir(process.argv.slice(2))

let files: string[]
try {
  files = readdirSync(REC_DIR).filter((f) => f.endsWith(".json") && !f.startsWith("_"))
} catch {
  console.error(`[diff-real-llm] recordings dir not readable: ${REC_DIR}`)
  console.error(`[diff-real-llm] record first: pnpm record:real-llm`)
  process.exit(1)
}

const records = new Map<string, ScenarioRecord>()
for (const f of files) {
  const r = JSON.parse(readFileSync(join(REC_DIR, f), "utf8")) as ScenarioRecord
  records.set(r.id, r)
}

interface Row {
  readonly id: string
  readonly cat: string
  readonly title: string
  readonly expDecision: string
  readonly actDecision: string
  readonly match: "✓" | "✗" | "—"
  readonly expMinTools: number
  readonly actTools: number
  readonly toolDelta: string
  readonly expApproval: boolean
  readonly actApproval: boolean
  readonly apprMatch: "✓" | "✗"
  readonly totalLatency: number
  readonly turns: number
  readonly replyLen: number
  readonly firstReplySnippet: string
  readonly notes: string
}

const rows: Row[] = []
let matches = 0
let approvalMatches = 0
let totalExpTools = 0
let totalActTools = 0

for (const sc of ALL_SCENARIOS) {
  const rec = records.get(sc.id)
  const expAppr = sc.expect.requireApproval ?? false
  if (!rec) {
    rows.push({
      id: sc.id,
      cat: sc.category,
      title: sc.title,
      expDecision: sc.expect.finalDecision ?? "—",
      actDecision: "MISSING",
      match: "✗",
      expMinTools: sc.expect.minToolCalls ?? 0,
      actTools: 0,
      toolDelta: "—",
      expApproval: expAppr,
      actApproval: false,
      apprMatch: "✗",
      totalLatency: 0,
      turns: 0,
      replyLen: 0,
      firstReplySnippet: "",
      notes: "no recording",
    })
    continue
  }
  const totalTools = rec.turns.reduce((s, t) => s + (t.toolCalls ?? 0), 0)
  const totalLatency = rec.turns.reduce((s, t) => s + t.latencyMs, 0)
  const replyLen = rec.turns.reduce((s, t) => s + t.replyLen, 0)
  const actDecision = rec.turns[0]?.finalDecision ?? "—"
  const expDecision = sc.expect.finalDecision ?? "—"
  const match =
    sc.expect.finalDecision === undefined
      ? "—"
      : actDecision === expDecision
        ? (matches++, "✓")
        : "✗"

  const expMin = sc.expect.minToolCalls ?? 0
  totalExpTools += expMin
  totalActTools += totalTools
  const toolDelta =
    expMin === 0 ? "—" : totalTools >= expMin ? `+${totalTools - expMin}` : `${totalTools - expMin}`

  const actAppr = rec.turns.some((t) => t.finalDecision === "WaitForApproval")
  const apprMatch = actAppr === expAppr ? (approvalMatches++, "✓") : "✗"

  // 探测 invalid JSON 痕迹（无 finalDecision 但有 reply）
  const degrade = !rec.turns[0]?.finalDecision && replyLen > 0
  const notes = degrade ? "no decision (degrade)" : ""

  const snippet = rec.turns[0]?.reply?.slice(0, 30).replace(/\n/g, " ") ?? ""

  rows.push({
    id: sc.id,
    cat: sc.category,
    title: sc.title,
    expDecision,
    actDecision,
    match,
    expMinTools: expMin,
    actTools: totalTools,
    toolDelta,
    expApproval: expAppr,
    actApproval: actAppr,
    apprMatch,
    totalLatency,
    turns: rec.turns.length,
    replyLen,
    firstReplySnippet: snippet,
    notes,
  })
}

const fmt = (n: number) => n.toLocaleString()
const decisionScored = rows.filter((r) => r.expDecision !== "—").length

console.log(`# Real LLM vs Fixture Diff`)
console.log()
console.log(`- source: \`${REC_DIR}\``)
console.log(`- scenarios: ${rows.length} (recorded ${records.size})`)
console.log(`- decision match: ${matches} / ${decisionScored}`)
console.log(`- approval match: ${approvalMatches} / ${rows.length}`)
console.log(
  `- tools: expected≥${totalExpTools}, actual=${totalActTools} (delta ${totalActTools - totalExpTools >= 0 ? "+" : ""}${totalActTools - totalExpTools})`,
)
console.log(`- total latency: ${fmt(rows.reduce((s, r) => s + r.totalLatency, 0))}ms`)
console.log()
console.log(
  `| ID | Cat | ExpDecision | ActDecision | Match | Tools(exp≥/act/Δ) | Approval(exp/act) | Latency(ms) | Turns | ReplyLen | Snippet | Notes |`,
)
console.log(`|---|---|---|---|---|---|---|---|---|---|---|---|`)
for (const r of rows) {
  console.log(
    `| ${r.id} | ${r.cat.split("-")[0]} | ${r.expDecision} | ${r.actDecision} | ${r.match} | ≥${r.expMinTools}/${r.actTools}/${r.toolDelta} | ${r.expApproval ? "Y" : "—"}/${r.actApproval ? "Y" : "—"} ${r.apprMatch} | ${fmt(r.totalLatency)} | ${r.turns} | ${r.replyLen} | ${r.firstReplySnippet} | ${r.notes} |`,
  )
}
console.log()
console.log(`## Decision mismatch`)
const mism = rows.filter((r) => r.match === "✗")
console.log(
  `- ${mism.length}: ${mism.map((r) => `${r.id}(exp ${r.expDecision}/act ${r.actDecision})`).join(", ") || "none"}`,
)
console.log()
console.log(`## Degrade cases (no decision)`)
const deg = rows.filter((r) => r.notes.includes("no decision"))
console.log(`- ${deg.length}: ${deg.map((r) => r.id).join(", ") || "none"}`)
console.log()
console.log(`## Tool calls over-shoot (more tools than fixture expected)`)
const overs = rows.filter((r) => r.toolDelta.startsWith("+"))
console.log(
  `- ${overs.length}: ${overs.map((r) => `${r.id}(+${r.actTools - r.expMinTools})`).join(", ") || "none"}`,
)
