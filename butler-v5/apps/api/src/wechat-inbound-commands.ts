import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import { tryWechatMemoryCommand } from "./wechat-memory-commands.js"
import { tryWechatProjectCommand } from "./wechat-project-surface.js"
import { tryWechatQualityGateCommand } from "./wechat-quality-gate.js"
import { tryWechatSubagentCommand } from "./wechat-subagent-commands.js"
import { tryWechatTaskCommand } from "./wechat-task-commands.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"
import type { Wiring } from "./wiring.js"

/**
 * Pre-loop WeChat slash commands: project surface, tasks, memory, quality gate, subagent.
 */
export async function tryWechatInboundCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<ButlerLoopResult | null> {
  const handlers = [
    () =>
      tryWechatProjectCommand({
        wiring: args.wiring,
        fromUserId: args.fromUserId,
        content: args.content,
        ...(args.env === undefined ? {} : { env: args.env }),
        ...(args.mcpBundle === undefined ? {} : { mcpBundle: args.mcpBundle }),
      }),
    () =>
      tryWechatTaskCommand({
        wiring: args.wiring,
        fromUserId: args.fromUserId,
        content: args.content,
        ...(args.env === undefined ? {} : { env: args.env }),
      }),
    () =>
      tryWechatMemoryCommand({
        wiring: args.wiring,
        fromUserId: args.fromUserId,
        content: args.content,
        ...(args.env === undefined ? {} : { env: args.env }),
      }),
    () =>
      tryWechatQualityGateCommand({
        fromUserId: args.fromUserId,
        content: args.content,
        ...(args.env === undefined ? {} : { env: args.env }),
        runtimeStore: args.wiring.runtimeStore,
      }),
    () =>
      tryWechatSubagentCommand({
        wiring: args.wiring,
        fromUserId: args.fromUserId,
        content: args.content,
        ...(args.env === undefined ? {} : { env: args.env }),
      }),
  ]

  for (const handler of handlers) {
    const result = await handler()
    if (result) return result
  }
  return null
}
