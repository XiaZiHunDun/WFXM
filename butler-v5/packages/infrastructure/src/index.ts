// ─── 持久化 ────────────────────────────────────────────────
export { events, outbox, intentReceipts, loadBearingMarks } from "./persistence/schema.js"
export { Db, DbLive, makeTestDb } from "./persistence/db.js"
export { DrizzleEventStoreLive, MockEventStoreLive } from "./persistence/eventstore-live.js"

// ─── 防错守卫（7 条核心 GUARD）─────────────────────────────
export {
  GuardServiceLive,
  simOwnerOffline,
  simOwnerOnline,
  registerLoadBearingMark,
  clearLoadBearingMarks,
  signPayload,
} from "./guards/index.js"

// ─── LLM 服务 ──────────────────────────────────────────────
export { LLMServiceLive, MockLLMLive } from "./llm/index.js"

// ─── 微信网关 ──────────────────────────────────────────────
export { WeChatGatewayLive, MockWeChatLive } from "./wechat/index.js"

// ─── MCP 发现 ──────────────────────────────────────────────
export { MCPDiscoveryLive, MockMCPDiscoveryLive } from "./mcp/index.js"

// ─── ACL 适配器 ────────────────────────────────────────────
export { V4Adapter, V4AdapterLive, MockV4AdapterLive } from "./acl/v4-adapter.js"

// ─── Layer 组合 ────────────────────────────────────────────
export { ProductionLayer, TestLayer } from "./layers.js"
