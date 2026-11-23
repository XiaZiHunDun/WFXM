/**
 * Shared Butler Runtime provider for every channel entry point.
 *
 * Owns the one assembly per process (lazy, failure not cached) and the
 * conversationId -> owner mapping used by detached task notifications.
 */
import type { ButlerMemoryPort } from "@butler/ports/core/butler-memory.js"
import type { ChannelKind } from "@butler/ports/core/channel.js"
import type { ButlerSubagentPort } from "@butler/ports/core/butler-subagent.js"
import type { TaskMemoryPort } from "@butler/ports/core/task-memory.js"
import { createButlerAssembly, type ButlerAssembly } from "./butler-assembly.js"
import { createTaskSettledNotifier, type TaskSettledPushResult } from "./butler-inbound.js"
import { parseProjectRoots } from "./butler-projects.js"
import { createButlerSubagentPort } from "./butler-subagent-port.js"
import {
  deliverSlackChannelReply,
  deliverTelegramChannelReply,
  slackBotToken,
  telegramBotToken,
} from "./channel-outbound.js"
import { envTruthy } from "./env-util.js"
import { resolveWechatProjectAlias } from "./wechat-active-project.js"
import { runQualityGate } from "./wechat-quality-gate.js"
import { sendWechatProactiveNotify } from "./wechat-run-notify.js"
import type { Wiring } from "./wiring.js"

/** Where a conversation's owner lives, used for proactive pushes. */
export interface ButlerOwnerRef {
  readonly channelKind: ChannelKind
  readonly address: string
  readonly threadTs?: string
}

export interface ButlerRuntimeProvider {
  /** One assembly per provider; a failed build is not cached. */
  assembly(): Promise<ButlerAssembly>
  /** Refreshed on every inbound turn so notifications follow the latest address. */
  rememberOwner(conversationId: string, owner: ButlerOwnerRef): void
}

export interface ButlerRuntimeProviderOptions {
  readonly env?: NodeJS.ProcessEnv
  /** agent-rag adapters; omitted when memory is not configured. */
  readonly memory?: {
    readonly butler?: ButlerMemoryPort
    readonly task?: TaskMemoryPort
  }
  /** Test seam: bypass env/model construction. */
  readonly createAssembly?: (
    wiring: Wiring,
    env: NodeJS.ProcessEnv,
  ) => ButlerAssembly | Promise<ButlerAssembly>
  /** Test seam / alternate transports for detached task notices. */
  readonly push?: (input: {
    readonly owner: ButlerOwnerRef
    readonly text: string
  }) => Promise<TaskSettledPushResult>
  /** Overrides the default project quality gate runner. */
  readonly qualityGate?: (input: {
    readonly projectId: string
    readonly nameFilter?: string
  }) => Promise<{ readonly reply: string; readonly traces?: readonly string[] }>
  /** Overrides the default subagent dispatch (e.g. in tests). */
  readonly subagent?: ButlerSubagentPort
}

/** Default proactive transport per channel kind. */
async function defaultProactivePush(
  owner: ButlerOwnerRef,
  text: string,
  env: NodeJS.ProcessEnv,
): Promise<TaskSettledPushResult> {
  switch (owner.channelKind) {
    case "wechat":
      return sendWechatProactiveNotify({ to: owner.address, text, env })
    case "slack": {
      // D74 T4: unwrap at the fetch call site so token flow stays reviewable.
      const token = slackBotToken(env).unwrap()
      if (!token) return { ok: false, reason: "BUTLER_V5_SLACK_BOT_TOKEN 未配置" }
      const result = await deliverSlackChannelReply({
        token,
        channel: owner.address,
        reply: text,
        ...(owner.threadTs === undefined ? {} : { threadTs: owner.threadTs }),
        env,
      })
      return result.delivered
        ? { ok: true }
        : { ok: false, reason: result.deliveryReason ?? "slack delivery failed" }
    }
    case "telegram": {
      const token = telegramBotToken(env).unwrap()
      if (!token) return { ok: false, reason: "BUTLER_V5_TELEGRAM_BOT_TOKEN 未配置" }
      const result = await deliverTelegramChannelReply({
        token,
        chatId: owner.address,
        reply: text,
        env,
      })
      return result.delivered
        ? { ok: true }
        : { ok: false, reason: result.deliveryReason ?? "telegram delivery failed" }
    }
    case "generic":
      return { ok: false, reason: "generic channel has no proactive transport" }
  }
}

export function createButlerRuntimeProvider(
  wiring: Wiring,
  options: ButlerRuntimeProviderOptions = {},
): ButlerRuntimeProvider {
  const env = options.env ?? process.env
  const owners = new Map<string, ButlerOwnerRef>()
  const detached = envTruthy(env["BUTLER_V5_DETACHED_TASKS"])
  const push =
    options.push ??
    ((input: { owner: ButlerOwnerRef; text: string }) =>
      defaultProactivePush(input.owner, input.text, env))
  const qualityGate =
    options.qualityGate ??
    ((input: { projectId: string; nameFilter?: string }) =>
      runQualityGate({
        projectId: input.projectId,
        ...(input.nameFilter === undefined ? {} : { nameFilter: input.nameFilter }),
        env,
        ...(wiring.runtimeStore === undefined ? {} : { runtimeStore: wiring.runtimeStore }),
      }))
  const subagent = options.subagent ?? createButlerSubagentPort(wiring, env)
  let cached: Promise<ButlerAssembly> | null = null

  async function assembly(): Promise<ButlerAssembly> {
    if (cached === null) {
      cached = Promise.resolve()
        .then(() =>
          options.createAssembly
            ? options.createAssembly(wiring, env)
            : createButlerAssembly({
                db: wiring.db,
                projects: parseProjectRoots(env),
                env,
                detachedTasks: detached,
                resolveProjectName: (raw) => resolveWechatProjectAlias(raw, env),
                ...(detached ? { onTaskSettled: notifier } : {}),
                ...(options.memory?.butler === undefined
                  ? {}
                  : { butlerMemory: options.memory.butler }),
                ...(options.memory?.task === undefined ? {} : { taskMemory: options.memory.task }),
                qualityGate,
                ...(subagent === undefined ? {} : { subagent }),
              }),
        )
        .catch((error: unknown) => {
          // Do not cache failures: a config fix + retry should work.
          cached = null
          throw error
        })
    }
    return cached
  }

  const notifier = createTaskSettledNotifier<ButlerOwnerRef>({
    approvalNotice: async (taskId) => (await assembly()).butler.approvalNotice(taskId),
    resolveOwner: (conversationId) => owners.get(conversationId),
    push: (input) => push({ owner: input.owner, text: input.text }),
  })

  return {
    assembly,
    rememberOwner(conversationId, owner) {
      owners.set(conversationId, owner)
    },
  }
}
