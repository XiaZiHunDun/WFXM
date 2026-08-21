// infrastructure/layers.ts
// Layer 组合 — 生产环境 Layer 合并

import { Layer } from "effect"
import { LLMServiceLive } from "../_archive/llm/index.js"
import { DrizzleEventStoreLive } from "./persistence/eventstore-live.js"
import { GuardServiceLive } from "./guards/index.js"
import { WeChatGatewayLive } from "../_archive/wechat/index.js"
import { MCPDiscoveryLive } from "./mcp/index.js"
import { ConfigLive } from "@butler/config"

// ─── 生产环境 Layer（单次 mergeAll 组合所有依赖） ────────
export const ProductionLayer = Layer.mergeAll(
  LLMServiceLive,
  DrizzleEventStoreLive,
  GuardServiceLive,
  WeChatGatewayLive,
  MCPDiscoveryLive,
  ConfigLive,
)

// ─── 测试用 Layer（Mock 实现） ───────────────────────────
export const TestLayer = Layer.mergeAll(
  LLMServiceLive,
  // Phase 4: 替换为 Mock 变体
  GuardServiceLive,
  WeChatGatewayLive,
  MCPDiscoveryLive,
  ConfigLive,
)
