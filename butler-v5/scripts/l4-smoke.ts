/**
 * L4 smoke: drive the real /v1/wechat/inbound route over HTTP and assert the
 * user-visible reply, without touching the WeChat channel at all.
 *
 * This is the "verification window" in front of the channel: same auth, same
 * intake, same butler runtime, same presentation layer as production, but the
 * message source is this script and the reply comes back in the HTTP body
 * instead of going out through iLink.
 *
 * Usage:
 *   cd butler-v5
 *   npx tsx scripts/l4-smoke.ts            # all cases
 *   npx tsx scripts/l4-smoke.ts --only 3   # one case
 *
 * The service must be running (systemctl --user status butler-v5-gateway) and
 * BUTLER_V5_INBOUND_SHARED_SECRET must be readable from the env or from
 * ~/.config/butler-v5/env.
 */
import { readFileSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"

type Case = {
  readonly id: number
  readonly name: string
  /** Messages sent in order inside one conversation. */
  readonly turns: readonly string[]
  /** Assertions applied to the LAST turn's reply. */
  readonly expect: {
    readonly mustMention?: readonly string[]
    readonly mustNotMatch?: readonly string[]
    readonly minLength?: number
    readonly maxLength?: number
  }
  /** Optional side effect the run must actually produce (delegated work). */
  readonly expectFile?: {
    readonly path: string
    readonly contains: string
    readonly timeoutMs: number
  }
  /** Override the sender when the path depends on owner identity (memory). */
  readonly sender?: string
}

function readEnvFile(): Record<string, string> {
  const out: Record<string, string> = {}
  try {
    const raw = readFileSync(join(homedir(), ".config", "butler-v5", "env"), "utf8")
    for (const line of raw.split("\n")) {
      const match = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim())
      if (match) out[match[1]!] = match[2]!
    }
  } catch {
    // File is optional; fall back to process.env.
  }
  return out
}

const envFile = readEnvFile()

/** Durable memory is keyed by the owner subject, not the raw sender. */
const ownerSender = (
  process.env["BUTLER_OWNER_WECHAT_ID"] ??
  envFile["BUTLER_OWNER_WECHAT_ID"] ??
  ""
).trim()

const CASES: readonly Case[] = [
  {
    id: 1,
    name: "规则回复：帮助",
    turns: ["帮助"],
    expect: {
      mustNotMatch: ["\\*\\*", "```", "^#{1,6} ", "\\bwrite\\b", "\\bedit\\b", "\\bbash\\b", "`"],
      minLength: 20,
      maxLength: 1800,
    },
  },
  {
    id: 2,
    name: "工具执行：列子包",
    turns: ["看看 butler-v5/packages 下有哪些子包，每个包一句话说明"],
    expect: {
      mustMention: ["domain", "ports", "adapters", "runtime", "persistence"],
      mustNotMatch: ["\\*\\*", "```", "`", "待执行：write", "待执行：bash"],
      minLength: 40,
      maxLength: 8000,
    },
  },
  {
    id: 3,
    name: "写文件：受理反馈 + 落盘结果",
    turns: ["在 butler-v5/.butler/l4-smoke.txt 写入 l4 ok"],
    expect: {
      mustMention: ["l4-smoke"],
      mustNotMatch: ["\\*\\*", "```", "`", "待执行：write"],
      maxLength: 1800,
    },
    expectFile: {
      path: ".butler/l4-smoke.txt",
      contains: "l4 ok",
      timeoutMs: 90_000,
    },
  },
  {
    id: 4,
    name: "多轮记忆：事实召回",
    // Durable memory is read under the owner subject, so this case must send
    // as the owner; it also proves the working-set injection path, since the
    // fact is new and cannot come from conversation history.
    sender: ownerSender,
    turns: [
      "记住：L4 验收标记是蓝鲸七号",
      "只根据你记住的内容回答，不要调用工具：L4 验收标记是什么？",
    ],
    expect: {
      mustMention: ["蓝鲸七号"],
      mustNotMatch: ["\\*\\*", "```", "`"],
      maxLength: 1800,
    },
  },
  {
    id: 5,
    name: "长回复：包名与描述",
    turns: ["把 butler-v5/packages 下每个包的 package.json 里 name 和 description 都列出来，一条一行，不要省略"],
    expect: {
      mustMention: ["@butler/domain", "@butler/ports", "@butler/adapters", "@butler/runtime", "@butler/persistence"],
      mustNotMatch: ["\\*\\*", "```", "`", "待执行：bash"],
      minLength: 120,
      maxLength: 8000,
    },
  },
]

const secret = (
  process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ??
  envFile["BUTLER_V5_INBOUND_SHARED_SECRET"] ??
  ""
).trim()
const baseUrl = (process.env["BUTLER_V5_SMOKE_BASE_URL"] ?? "http://127.0.0.1:3000").trim()
const sender = "l4-smoke@im.wechat"

if (!secret) {
  console.error("missing BUTLER_V5_INBOUND_SHARED_SECRET (env or ~/.config/butler-v5/env)")
  process.exit(2)
}

type TurnResult = { readonly ok: boolean; readonly reply: string; readonly ms: number; readonly error?: string }

async function sendTurn(
  conversation: string,
  text: string,
  seq: number,
  fromUserId: string,
): Promise<TurnResult> {
  const started = Date.now()
  try {
    const res = await fetch(`${baseUrl}/v1/wechat/inbound`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-inbound-secret": secret },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId,
        content: text,
        messageId: `${conversation}-${seq}`,
        conversationId: conversation,
      }),
    })
    const raw = await res.text()
    const ms = Date.now() - started
    if (!res.ok) {
      return { ok: false, reply: raw.slice(0, 200), ms, error: `HTTP ${res.status}` }
    }
    const parsed = JSON.parse(raw) as { reply?: unknown }
    if (typeof parsed.reply !== "string" || !parsed.reply) {
      return { ok: false, reply: "", ms, error: "response has no reply" }
    }
    return { ok: true, reply: parsed.reply, ms }
  } catch (err) {
    return { ok: false, reply: "", ms: Date.now() - started, error: String(err) }
  }
}

function check(reply: string, expect: Case["expect"]): string[] {
  const failures: string[] = []
  // Invariants for every owner-facing reply, independent of the case.
  for (const jargon of ["子代理", "开发验收", "Durable Memory", "Project Knowledge"]) {
    if (reply.includes(jargon)) failures.push(`leaked internal term "${jargon}"`)
  }
  for (const needle of expect.mustMention ?? []) {
    if (!reply.includes(needle)) failures.push(`missing "${needle}"`)
  }
  for (const pattern of expect.mustNotMatch ?? []) {
    if (new RegExp(pattern, "m").test(reply)) failures.push(`matched forbidden /${pattern}/`)
  }
  if (expect.minLength !== undefined && reply.length < expect.minLength) {
    failures.push(`too short (${reply.length} < ${expect.minLength})`)
  }
  if (expect.maxLength !== undefined && reply.length > expect.maxLength) {
    failures.push(`too long (${reply.length} > ${expect.maxLength})`)
  }
  if (!reply.trim()) failures.push("empty reply")
  return failures
}

async function waitForFile(spec: NonNullable<Case["expectFile"]>): Promise<string[]> {
  const deadline = Date.now() + spec.timeoutMs
  while (Date.now() < deadline) {
    try {
      const content = readFileSync(spec.path, "utf8")
      return content.includes(spec.contains) ? [] : [`${spec.path} content missing "${spec.contains}"`]
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
  }
  return [`file not created within ${spec.timeoutMs}ms: ${spec.path}`]
}

async function main(): Promise<void> {
  const onlyArg = process.argv.indexOf("--only")
  const only = onlyArg >= 0 ? Number(process.argv[onlyArg + 1]) : undefined
  const selected = only === undefined ? CASES : CASES.filter((entry) => entry.id === only)
  if (selected.length === 0) {
    console.error(`no case with id ${String(only)}`)
    process.exit(2)
  }

  let failed = 0
  for (const entry of selected) {
    const conversation = `l4-smoke-${entry.id}-${Date.now()}`
    const from = entry.sender ?? sender
    let last: TurnResult | undefined
    for (const [index, text] of entry.turns.entries()) {
      last = await sendTurn(conversation, text, index + 1, from)
      const preview = (last.reply || last.error || "").replace(/\s+/g, " ").slice(0, 120)
      console.log(`      turn ${index + 1} "${text.slice(0, 20)}" ${last.ms}ms > ${preview}`)
      if (!last.ok) break
    }
    const replyFailures = last?.ok ? check(last.reply, entry.expect) : [last?.error ?? "no reply"]
    const fileFailures = entry.expectFile ? await waitForFile(entry.expectFile) : []
    const failures = [...replyFailures, ...fileFailures]
    const passed = failures.length === 0
    if (!passed) failed += 1
    const preview = (last?.reply ?? "").replace(/\s+/g, " ").slice(0, 160)
    console.log(
      `${passed ? "PASS" : "FAIL"}  L4-${entry.id}  ${entry.name}  ${last?.ms ?? 0}ms` +
        (failures.length ? `\n      ${failures.join("; ")}` : "") +
        `\n      > ${preview}`,
    )
  }
  console.log(`\n${selected.length - failed}/${selected.length} passed`)
  process.exit(failed === 0 ? 0 : 1)
}

main().catch((err: unknown) => {
  console.error(err)
  process.exit(1)
})
