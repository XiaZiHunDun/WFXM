#!/usr/bin/env node
/* eslint-disable no-console -- CLI entrypoint: stdout is the product interface */
/**
 * `pnpm demo` — Butler v5 zero-LLM CLI REPL.
 *
 * 复用 acceptance harness（makeAcceptanceApp）+ 脚本化 fixture LLM，
 * 在本进程内启动生产 wiring + 内存 PGlite + Hono 路由。无需 Docker /
 * PostgreSQL / ANTHROPIC_API_KEY。
 *
 * 用法：
 *   cd butler-v5
 *   pnpm demo
 *
 * 交互：
 *   输入 owner 消息 → POST /v1/wechat/inbound → 打印 bot 回复
 *   /help 显示帮助，/reset 清空会话，/audit 看 run 数，/quit 退出
 *
 * Self-hosting / 真 LLM 启动见 → ../../docs/deployment/SELF-HOSTING.md（D79 T3）。
 */
import { createInterface, type Interface as RLInterface } from 'node:readline'
import { makeAcceptanceApp, type AcceptanceApp } from '../tests/acceptance/harness.js'

// ---------------------------------------------------------------------------
// Fixtures — 脚本化"好 bot"模式：循环响应 + 偶发写工具。
// 跑完 n 轮后 LLM fixture 触发 exhausted，bot 返回 "[fixture exhausted]"。
// ---------------------------------------------------------------------------

interface FixtureEntry {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason: 'end_turn' | 'tool_use' | 'stop' | 'max_tokens'
}

const text = (content: string): FixtureEntry => ({
  content,
  toolCalls: [],
  stopReason: 'end_turn',
})

const toolCall = (name: string, args: Record<string, unknown>, id = 'tc-1'): FixtureEntry => ({
  content: '',
  toolCalls: [{ id, name, args }],
  stopReason: 'tool_use',
})

const N = 12

const DEMO_FIXTURES = {
  plan: [
    text('已收到（demo plan #1）。这是脚本化 LLM 应答。'),
    text('demo plan #2。已走通 plan → exec 链路。'),
    toolCall('write_file', { path: '/tmp/demo-write.txt', content: 'demo write' }),
    text('demo plan #4（写文件后会触发 approval）。'),
    ...Array.from({ length: N - 4 }, (_, i) => text(`demo plan 第 ${i + 5} 次循环。`)),
  ],
  exec: [
    text('demo exec #1。'),
    text('demo exec #2。'),
    text('✅ demo: 已写入 /tmp/demo-write.txt。'),
    ...Array.from({ length: N - 3 }, (_, i) => text(`demo exec 第 ${i + 4} 次循环。`)),
  ],
  intake: Array.from({ length: N }, (_, i) => text(`demo intake 第 ${i + 1} 次分类。`)),
}

// ---------------------------------------------------------------------------
// REPL loop
// ---------------------------------------------------------------------------

const HELP_TEXT = `
Butler v5 demo (zero-LLM REPL)
=========================
脚本化 fixture LLM + 内存 PGlite，无需 ANTHROPIC_API_KEY / Docker / Postgres。

快捷命令：
  /help   显示帮助
  /reset  清空 conversationId（开始新会话）
  /audit  显示当前会话 run 数
  /quit   退出（Ctrl+C 同效）

输入 owner 消息直接发即可，例如：
  帮我读 README.md
  最近 3 天做了什么
  改 foo.ts 加 log
`

async function main(): Promise<void> {
  const app: AcceptanceApp = await makeAcceptanceApp()
  app.setFixtures(DEMO_FIXTURES)

  let conversationId: string | undefined
  let runCount = 0

  const rl: RLInterface = createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  })
  console.log(HELP_TEXT)

  const inflight: { current: Promise<void> } = { current: Promise.resolve() }

  const shutdown = async (): Promise<void> => {
    await inflight.current
    rl.close()
    await app.close()
    process.exit(0)
  }
  process.on('SIGINT', () => {
    void shutdown()
  })
  process.on('SIGTERM', () => {
    void shutdown()
  })

  const processLine = async (raw: string): Promise<void> => {
    const input = raw.trim()
    if (!input) return
    if (input === '/help') {
      console.log(HELP_TEXT)
      return
    }
    if (input === '/quit' || input === '/exit') {
      void shutdown()
      return
    }
    if (input === '/reset') {
      conversationId = undefined
      runCount = 0
      console.log('--- conversation reset ---')
      return
    }
    if (input === '/audit') {
      console.log(`--- runs in current session: ${runCount} ---`)
      return
    }

    try {
      const result = await sendTurn(app, input, conversationId)
      if (result.conversationId) conversationId = result.conversationId
      runCount += 1
      const tail =
        result.finalDecision !== undefined
          ? `\n  [${result.finalDecision}${result.toolCalls !== undefined ? ` · ${result.toolCalls} tools` : ''}]`
          : ''
      console.log(`< ${result.reply}${tail}`)
    } catch (err) {
      console.error(`! error: ${(err as Error).message}`)
    }
  }

  rl.on('line', (raw: string) => {
    inflight.current = inflight.current
      .then(() => processLine(raw))
      .catch((err: unknown) => {
        console.error(`! error: ${(err as Error).message}`)
      })
  })

  // /quit handled last (sequential) to ensure no in-flight reply is lost.
  rl.on('close', () => {
    void shutdown()
  })
}

interface TurnResult {
  readonly conversationId?: string
  readonly reply: string
  readonly finalDecision?: string
  readonly toolCalls?: number
}

async function sendTurn(
  app: AcceptanceApp,
  input: string,
  conversationId: string | undefined,
): Promise<TurnResult> {
  const res = await app.request('/v1/wechat/inbound', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      // acceptance harness 设了 BUTLER_V5_INBOUND_SHARED_SECRET=test-inbound-secret-9c2f
      'x-inbound-secret': 'test-inbound-secret-9c2f',
    },
    body: JSON.stringify({
      apiVersion: 'v1',
      fromUserId: 'u-owner',
      content: input,
      messageId: `m-demo-${Date.now()}`,
      ...(conversationId !== undefined ? { conversationId } : {}),
      projectId: 'wechat',
    }),
  })
  const text = await res.text()
  let parsed:
    | {
        readonly conversationId?: string
        readonly reply?: string
        readonly meta?: { readonly finalDecision?: string; readonly toolCalls?: number }
      }
    | undefined
  try {
    parsed = JSON.parse(text) as typeof parsed
  } catch {
    parsed = undefined
  }
  return {
    ...(parsed?.conversationId !== undefined ? { conversationId: parsed.conversationId } : {}),
    reply: parsed?.reply ?? text,
    ...(parsed?.meta?.finalDecision !== undefined ? { finalDecision: parsed.meta.finalDecision } : {}),
    ...(parsed?.meta?.toolCalls !== undefined ? { toolCalls: parsed.meta.toolCalls } : {}),
  }
}

main().catch((err: unknown) => {
  console.error('demo failed:', err)
  process.exit(1)
})