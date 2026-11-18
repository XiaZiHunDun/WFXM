// wechat-mock.mjs — 微信 API Mock（Phase 0 开发用）
// 监听 3001 端口，模拟微信消息收发

import { createServer } from "node:http"

const PORT = process.env.PORT ?? 3001

const server = createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "application/json" })
  res.end(JSON.stringify({ errcode: 0, errmsg: "ok" }))
})

server.listen(PORT, () => {
  console.log(`[wechat-mock] listening on :${PORT}`)
})
