// infrastructure/layers.ts — Effect Layer 组合示例（无生产消费者）

import { Layer } from "effect"
import { LLMServiceLive } from "../_archive/llm/index.js"
import { DrizzleEventStoreLive } from "../_archive/persistence/eventstore-live.js"
import { GuardServiceLive } from "../_archive/guards/index.js"
import { WeChatGatewayLive } from "../_archive/wechat/index.js"
import { MCPDiscoveryLive } from "../_archive/mcp/index.js"
import { ConfigLive } from "@butler/config"

export const ProductionLayer = Layer.mergeAll(
  LLMServiceLive,
  DrizzleEventStoreLive,
  GuardServiceLive,
  WeChatGatewayLive,
  MCPDiscoveryLive,
  ConfigLive,
)

export const TestLayer = Layer.mergeAll(
  LLMServiceLive,
  GuardServiceLive,
  WeChatGatewayLive,
  MCPDiscoveryLive,
  ConfigLive,
)
