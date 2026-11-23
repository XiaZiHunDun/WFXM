/**
 * ButlerSubagentPort backed by the existing delegate tool.
 *
 * The delegate runtime owns capability checks, audit logging and child-run
 * creation; this adapter only binds a butler turn to that tool.
 */
import type {
  ButlerSubagentPort,
  ButlerSubagentResult,
} from "@butler/ports/core/butler-subagent.js"
import { isSubagentEnabled } from "./subagent-config.js"
import { makeDelegateToSubagentTool } from "./tools.js"
import type { Wiring } from "./wiring.js"

export function createButlerSubagentPort(
  wiring: Wiring,
  env: NodeJS.ProcessEnv = process.env,
): ButlerSubagentPort | undefined {
  if (!isSubagentEnabled(env)) return undefined
  return {
    async delegate(input): Promise<ButlerSubagentResult> {
      const tool = makeDelegateToSubagentTool({
        bridge: wiring.eventBridge,
        conversationId: input.conversationId,
        actor: { kind: "agent", id: "butler" },
        runtimeStore: wiring.runtimeStore,
        wechatUserId: input.userId,
        env,
      })
      const outcome = await tool.run({
        task: input.task,
        ...(input.role === undefined ? {} : { role: input.role }),
        ...(input.capabilities === undefined ? {} : { capabilities: input.capabilities }),
      })
      if (!outcome.ok) return { ok: false, reason: outcome.reason }
      const output = outcome.output
      return { ok: true, output: typeof output === "string" ? output : JSON.stringify(output) }
    },
  }
}
