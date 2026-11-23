#!/usr/bin/env node
/* eslint-disable no-console -- CLI entrypoint: stdout is the product interface */
/**
 * `pnpm demo:web` — Butler v5 本地浏览器 Demo 控制台。
 *
 * 复用 acceptance harness（makeAcceptanceApp）+ 脚本化 fixture LLM + 内存
 * PGlite，在本进程内起生产 wiring，再用 `node:http` 暴露一个仅绑定
 * 127.0.0.1 的控制台：
 *
 *   GET  /                                内联 HTML 控制台
 *   GET  /health                          健康检查
 *   POST /demo/api/chat                   发消息（代理 /v1/wechat/inbound）
 *   GET  /demo/api/approvals              待审批列表
 *   POST /demo/api/approvals/:id/approve  批准
 *   POST /demo/api/approvals/:id/deny     拒绝
 *   POST /demo/api/reset                  重建 app + 清空会话
 *
 * 安全边界：只绑 loopback、不调真实模型、不读真实 API key、write_file 落在
 * harness 的临时工作区。owner 路由依赖 socket remoteAddress；这里通过
 * `app.fetch(req, LOOPBACK_ENV)` 显式声明 loopback（与监听地址一致）。
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http"
import { makeAcceptanceApp, type AcceptanceApp } from "../tests/acceptance/harness.js"

const HOST = "127.0.0.1"
const DEFAULT_PORT = 4520
const MAX_BODY_BYTES = 16 * 1024
const MAX_MESSAGE_CHARS = 2000
/** owner 路由从 env.incoming.socket.remoteAddress 判定 loopback。 */
const LOOPBACK_ENV = { incoming: { socket: { remoteAddress: HOST } } } as const

interface FixtureEntry {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason: "end_turn" | "tool_use" | "stop" | "max_tokens"
}

const text = (content: string): FixtureEntry => ({
  content,
  toolCalls: [],
  stopReason: "end_turn",
})

const toolCall = (name: string, args: Record<string, unknown>, id: string): FixtureEntry => ({
  content: "",
  toolCalls: [{ id, name, args }],
  stopReason: "tool_use",
})

/**
 * 确定性剧本：
 *   第 1 轮 → 文本回复
 *   第 2 轮 → write_file（命中 alwaysConfirm → WaitForApproval）
 *   第 3 轮 → 文本回复
 */
const DEMO_FIXTURES = {
  plan: [
    text("你好，我是 Butler v5 demo。当前使用脚本化 LLM，不会调用真实模型。"),
    toolCall(
      "write_file",
      { path: "demo-note.txt", content: "hello from demo console" },
      "tc-demo-write",
    ),
    text("已经处理完毕（demo 第三轮）。"),
  ],
  exec: [text("✅ 已写入 demo-note.txt。"), text("demo exec 循环。")],
  intake: [text("chat")],
}

function inboundSecret(): string {
  return process.env["BUTLER_V5_INBOUND_SHARED_SECRET"] ?? "test-inbound-secret-9c2f"
}

class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

let app: AcceptanceApp
let conversationId: string | undefined
let messageSeq = 0
let queue: Promise<unknown> = Promise.resolve()

/** 串行执行：避免 reset 与在途 chat/approve 交错。 */
function serialize<T>(task: () => Promise<T>): Promise<T> {
  const run = queue.then(() => task())
  queue = run.then(
    () => undefined,
    () => undefined,
  )
  return run
}

async function rebuild(): Promise<void> {
  await app.close()
  app = await makeAcceptanceApp()
  app.setFixtures(DEMO_FIXTURES)
}

async function callApp(path: string, init?: RequestInit): Promise<Response> {
  const url = "http://" + HOST + ":" + port + path
  return app.fetch(new Request(url, init), LOOPBACK_ENV)
}

async function listPending(): Promise<readonly unknown[]> {
  const res = await callApp("/v1/owner/approvals")
  if (!res.ok) return []
  const raw = await res.text()
  try {
    const parsed = JSON.parse(raw) as { items?: unknown[] }
    return Array.isArray(parsed.items) ? parsed.items : []
  } catch {
    return []
  }
}

interface ChatResult {
  readonly reply: string
  readonly conversationId?: string
  readonly finalDecision?: string
  readonly toolCalls?: number
  readonly pending: readonly unknown[]
}

async function chat(content: string): Promise<ChatResult> {
  const body = {
    apiVersion: "v1",
    fromUserId: "u-owner",
    content,
    messageId: "m-demo-" + Date.now() + "-" + (messageSeq += 1),
    ...(conversationId !== undefined ? { conversationId } : {}),
    projectId: "wechat",
  }
  const res = await callApp("/v1/wechat/inbound", {
    method: "POST",
    headers: { "content-type": "application/json", "x-inbound-secret": inboundSecret() },
    body: JSON.stringify(body),
  })
  const raw = await res.text()
  if (!res.ok) throw new HttpError(res.status, "入站失败：" + raw.slice(0, 300))
  let parsed: {
    conversationId?: string
    reply?: string
    meta?: { finalDecision?: string; toolCalls?: number }
  } = {}
  try {
    parsed = JSON.parse(raw) as typeof parsed
  } catch {
    // 非 JSON 时退回原文，交给上层展示。
  }
  if (typeof parsed.conversationId === "string") conversationId = parsed.conversationId
  return {
    reply: parsed.reply ?? raw,
    ...(parsed.conversationId !== undefined ? { conversationId: parsed.conversationId } : {}),
    ...(parsed.meta?.finalDecision !== undefined
      ? { finalDecision: parsed.meta.finalDecision }
      : {}),
    ...(parsed.meta?.toolCalls !== undefined ? { toolCalls: parsed.meta.toolCalls } : {}),
    pending: await listPending(),
  }
}

async function decide(stepId: string, action: "approve" | "deny"): Promise<unknown> {
  const res = await callApp("/v1/owner/approvals/" + encodeURIComponent(stepId) + "/" + action, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  })
  const raw = await res.text()
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    parsed = { ok: false, reason: raw }
  }
  if (!res.ok) throw new HttpError(res.status, "审批操作失败：" + raw.slice(0, 300))
  return parsed
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(payload),
    "cache-control": "no-store",
  })
  res.end(payload)
}

function sendHtml(res: ServerResponse, html: string): void {
  res.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "content-length": Buffer.byteLength(html),
    "cache-control": "no-store",
  })
  res.end(html)
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req) {
    const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as Uint8Array)
    size += buf.length
    if (size > MAX_BODY_BYTES) throw new HttpError(413, "请求体过大")
    chunks.push(buf)
  }
  if (size === 0) return {}
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown
  } catch {
    throw new HttpError(400, "请求体不是合法 JSON")
  }
}

async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? "/", "http://" + HOST + ":" + port)
  const path = url.pathname

  if (req.method === "GET" && path === "/") {
    sendHtml(res, DASHBOARD_HTML)
    return
  }
  if (req.method === "GET" && path === "/health") {
    sendJson(res, 200, { ok: true, app: "butler-demo" })
    return
  }
  if (req.method === "GET" && path === "/demo/api/approvals") {
    sendJson(res, 200, { ok: true, items: await serialize(listPending) })
    return
  }
  if (req.method === "POST" && path === "/demo/api/chat") {
    const body = (await readJson(req)) as { content?: unknown }
    const content = typeof body.content === "string" ? body.content.trim() : ""
    if (!content) throw new HttpError(400, "消息不能为空")
    if (content.length > MAX_MESSAGE_CHARS) {
      throw new HttpError(400, "消息过长（上限 " + MAX_MESSAGE_CHARS + " 字）")
    }
    const result = await serialize(() => chat(content))
    sendJson(res, 200, { ok: true, ...result })
    return
  }
  if (req.method === "POST" && path === "/demo/api/reset") {
    const pending = await serialize(async () => {
      conversationId = undefined
      await rebuild()
      return [] as readonly unknown[]
    })
    sendJson(res, 200, { ok: true, pending })
    return
  }
  const decideMatch = /^\/demo\/api\/approvals\/([^/]+)\/(approve|deny)$/.exec(path)
  if (req.method === "POST" && decideMatch) {
    const stepId = decodeURIComponent(decideMatch[1] ?? "")
    const action = decideMatch[2] === "approve" ? "approve" : "deny"
    await readJson(req)
    const decision = await serialize(() => decide(stepId, action))
    const pending = await serialize(listPending)
    sendJson(res, 200, { ok: true, decision, pending })
    return
  }
  throw new HttpError(404, "未知路径：" + path)
}

const port = Number.parseInt(process.env["BUTLER_V5_DEMO_PORT"] ?? "", 10) || DEFAULT_PORT

async function main(): Promise<void> {
  app = await makeAcceptanceApp()
  app.setFixtures(DEMO_FIXTURES)

  const server = createServer((req, res) => {
    void route(req, res).catch((err: unknown) => {
      const status = err instanceof HttpError ? err.status : 500
      const reason = err instanceof Error ? err.message : String(err)
      if (!res.headersSent) {
        sendJson(res, status, { ok: false, reason })
      } else {
        res.end()
      }
    })
  })
  await new Promise<void>((resolve) => server.listen(port, HOST, resolve))

  console.log("Butler v5 demo console → http://" + HOST + ":" + port)
  console.log("脚本化 LLM · 内存 PGlite · 不调用真实模型。Ctrl+C 退出。")

  const shutdown = (signal: string): void => {
    console.log("\n收到 " + signal + "，正在关闭…")
    server.close(() => {
      void app.close().finally(() => process.exit(0))
    })
    setTimeout(() => process.exit(0), 5000).unref()
  }
  process.on("SIGINT", () => shutdown("SIGINT"))
  process.on("SIGTERM", () => shutdown("SIGTERM"))
}

const DASHBOARD_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Butler v5 Demo Console</title>
<style>
  :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --ink:#1b1f24; --muted:#6b7280; --line:#e5e7eb; --accent:#2563eb; --bot:#eef2ff; --user:#2563eb; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--ink); }
  header { display:flex; align-items:center; gap:16px; padding:16px 24px; background:var(--panel); border-bottom:1px solid var(--line); }
  h1 { font-size:18px; margin:0; }
  .sub { margin:0; color:var(--muted); font-size:12px; }
  .actions { margin-left:auto; display:flex; align-items:center; gap:12px; }
  #status { font-size:13px; color:var(--muted); }
  #status.error { color:#b91c1c; }
  button { border:1px solid var(--line); background:var(--panel); color:var(--ink); border-radius:8px; padding:8px 14px; font-size:13px; cursor:pointer; }
  button:hover:not(:disabled) { border-color:#c7cbd1; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  main { display:grid; grid-template-columns: minmax(0,1fr) 320px; gap:16px; padding:16px 24px; height:calc(100vh - 73px); }
  .chat { display:flex; flex-direction:column; background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  .transcript { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:10px; }
  .bubble { max-width:78%; padding:10px 12px; border-radius:12px; background:var(--bot); align-self:flex-start; }
  .bubble.user { background:var(--user); color:#fff; align-self:flex-end; }
  .who { display:block; font-size:11px; opacity:.7; margin-bottom:4px; }
  .bubble p { margin:0; white-space:pre-wrap; font-size:14px; line-height:1.5; }
  .composer { display:flex; gap:8px; padding:12px; border-top:1px solid var(--line); }
  .composer input { flex:1; padding:10px 12px; border:1px solid var(--line); border-radius:8px; font-size:14px; outline:none; }
  .composer input:focus { border-color:var(--accent); }
  .approvals { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px; overflow-y:auto; }
  .approvals h2 { margin:0 0 12px; font-size:15px; }
  #pending-count { color:var(--accent); }
  .approval { border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:10px; }
  .approval .cap { font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; color:var(--accent); }
  .approval .q { font-size:13px; margin:6px 0 10px; line-height:1.5; }
  .approval .btns { display:flex; gap:8px; }
  .empty { color:var(--muted); font-size:13px; }
  @media (max-width: 860px) { main { grid-template-columns:1fr; height:auto; } }
</style>
</head>
<body>
<header>
  <div>
    <h1>Butler v5 Demo Console</h1>
    <p class="sub">脚本化 LLM · 内存数据库 · 仅本机</p>
  </div>
  <div class="actions">
    <span id="status" data-testid="status">就绪</span>
    <button id="reset" data-testid="reset">重置会话</button>
  </div>
</header>
<main>
  <section class="chat">
    <div id="transcript" data-testid="transcript" class="transcript"></div>
    <form id="composer" class="composer">
      <input id="input" data-testid="input" type="text" autocomplete="off" maxlength="2000" placeholder="输入消息，例如：你好" aria-label="消息内容">
      <button id="send" data-testid="send" class="primary" type="submit">发送</button>
    </form>
  </section>
  <aside class="approvals">
    <h2>待审批 <span id="pending-count" data-testid="pending-count">0</span></h2>
    <div id="approvals" data-testid="approvals"></div>
  </aside>
</main>
<script>
(function () {
  var transcript = document.getElementById('transcript')
  var form = document.getElementById('composer')
  var input = document.getElementById('input')
  var send = document.getElementById('send')
  var statusEl = document.getElementById('status')
  var approvalsEl = document.getElementById('approvals')
  var countEl = document.getElementById('pending-count')
  var resetBtn = document.getElementById('reset')
  var busy = false

  function setStatus(text, isError) {
    statusEl.textContent = text
    statusEl.className = isError ? 'error' : ''
  }
  function setBusy(next) {
    busy = next
    send.disabled = next
    resetBtn.disabled = next
  }
  function bubble(role, text) {
    var div = document.createElement('div')
    div.className = 'bubble ' + role
    div.setAttribute('data-testid', role === 'user' ? 'bubble-user' : 'bubble-bot')
    var who = document.createElement('span')
    who.className = 'who'
    who.textContent = role === 'user' ? '你' : 'Butler'
    var p = document.createElement('p')
    p.textContent = text
    div.appendChild(who)
    div.appendChild(p)
    transcript.appendChild(div)
    transcript.scrollTop = transcript.scrollHeight
    return div
  }
  function stringify(value) {
    if (value === undefined || value === null) return ''
    return typeof value === 'string' ? value : JSON.stringify(value)
  }
  function renderPending(items) {
    approvalsEl.textContent = ''
    countEl.textContent = String(items.length)
    if (items.length === 0) {
      var empty = document.createElement('p')
      empty.className = 'empty'
      empty.setAttribute('data-testid', 'approval-empty')
      empty.textContent = '无待审批'
      approvalsEl.appendChild(empty)
      return
    }
    items.forEach(function (item) {
      var card = document.createElement('div')
      card.className = 'approval'
      card.setAttribute('data-testid', 'approval-item')
      var cap = document.createElement('div')
      cap.className = 'cap'
      cap.textContent = item.capability || item.kind || 'tool'
      var q = document.createElement('div')
      q.className = 'q'
      q.textContent = item.question || ('资源：' + (item.resource || '未知'))
      var btns = document.createElement('div')
      btns.className = 'btns'
      var approve = document.createElement('button')
      approve.className = 'primary'
      approve.setAttribute('data-action', 'approve')
      approve.setAttribute('data-step', item.id)
      approve.textContent = '批准'
      var deny = document.createElement('button')
      deny.setAttribute('data-action', 'deny')
      deny.setAttribute('data-step', item.id)
      deny.textContent = '拒绝'
      btns.appendChild(approve)
      btns.appendChild(deny)
      card.appendChild(cap)
      card.appendChild(q)
      card.appendChild(btns)
      approvalsEl.appendChild(card)
    })
  }
  function request(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (res) {
      return res.text().then(function (raw) {
        var data = {}
        try { data = JSON.parse(raw) } catch (e) { data = { ok: false, reason: raw } }
        if (!res.ok || data.ok === false) {
          throw new Error(data.reason || ('请求失败（' + res.status + '）'))
        }
        return data
      })
    })
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault()
    var content = input.value.trim()
    if (!content || busy) return
    bubble('user', content)
    input.value = ''
    setBusy(true)
    setStatus('处理中…')
    request('/demo/api/chat', { content: content }).then(function (data) {
      bubble('bot', data.reply || '（空回复）')
      renderPending(Array.isArray(data.pending) ? data.pending : [])
      setStatus(data.finalDecision === 'WaitForApproval' ? '等待审批' : '就绪')
    }).catch(function (err) {
      setStatus(err.message, true)
    }).then(function () {
      setBusy(false)
      input.focus()
    })
  })

  approvalsEl.addEventListener('click', function (event) {
    var btn = event.target.closest('button[data-action]')
    if (!btn || busy) return
    var stepId = btn.getAttribute('data-step')
    var action = btn.getAttribute('data-action')
    setBusy(true)
    request('/demo/api/approvals/' + encodeURIComponent(stepId) + '/' + action, {}).then(function (data) {
      var decision = data.decision || {}
      var label = action === 'approve' ? '已批准' : '已拒绝'
      var detail = stringify(decision.output) || stringify(decision.reason)
      bubble('bot', label + (detail ? '：' + detail : ''))
      renderPending(Array.isArray(data.pending) ? data.pending : [])
      setStatus(label)
    }).catch(function (err) {
      setStatus(err.message, true)
    }).then(function () {
      setBusy(false)
    })
  })

  resetBtn.addEventListener('click', function () {
    if (busy) return
    setBusy(true)
    setStatus('重置中…')
    request('/demo/api/reset', {}).then(function (data) {
      transcript.textContent = ''
      renderPending(Array.isArray(data.pending) ? data.pending : [])
      setStatus('会话已重置')
    }).catch(function (err) {
      setStatus(err.message, true)
    }).then(function () {
      setBusy(false)
      input.focus()
    })
  })

  fetch('/demo/api/approvals').then(function (res) {
    return res.json()
  }).then(function (data) {
    renderPending(Array.isArray(data.items) ? data.items : [])
  }).catch(function () {})

  bubble('bot', '欢迎使用 Butler v5 Demo 控制台。输入消息开始体验。')
  input.focus()
})()
</script>
</body>
</html>
`

main().catch((err: unknown) => {
  console.error("demo server 启动失败：", err)
  process.exit(1)
})
