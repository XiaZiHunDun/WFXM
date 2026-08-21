// infrastructure — Effect Layer 示例入口（无生产消费者）

export { ProductionLayer, TestLayer } from "./layers.js"

// 归档模块 re-export（仅供包内测试 / 历史参考）
export {
  GuardServiceLive,
  simOwnerOffline,
  simOwnerOnline,
  registerLoadBearingMark,
  clearLoadBearingMarks,
  signPayload,
} from "../_archive/guards/index.js"
export { events, outbox, intentReceipts, loadBearingMarks } from "../_archive/persistence/schema.js"
export { Db, DbLive, makeTestDb } from "../_archive/persistence/db.js"
export { DrizzleEventStoreLive, MockEventStoreLive } from "../_archive/persistence/eventstore-live.js"
export { LLMServiceLive, MockLLMLive } from "../_archive/llm/index.js"
export { WeChatGatewayLive, MockWeChatLive } from "../_archive/wechat/index.js"
export { MCPDiscoveryLive, MockMCPDiscoveryLive } from "../_archive/mcp/index.js"
export { V4Adapter, V4AdapterLive, MockV4AdapterLive } from "../_archive/acl/v4-adapter.js"
