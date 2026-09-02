/**
 * WeChat inbound intent classification and routing (P2).
 *
 * Deterministic rules first; optional LLM intake when BUTLER_V5_INTAKE_LLM=1.
 */
import type { RunTrigger } from "@butler/domain/runtime.js"
import { buildWechatRunTrigger } from "@butler/domain/runtime.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import { runButlerLoop } from "./wechat-inbound-butler.js"
import {
  ensureDevSessionGrants,
  formatDevSessionEnabledReply,
  isDevSessionPhrase,
} from "./dev-session-grant.js"
import {
  getWechatActiveProjectId,
  parseWechatProjectCatalog,
  resolveWechatProjectAlias,
  setWechatActiveProjectId,
} from "./wechat-active-project.js"
import { normalizeWechatSwitchCommand } from "./wechat-project-switch.js"
import { summarizeWechatToolProfile } from "./wechat-project-surface.js"
import { resolveProjectKnowledgeInboundProjectId } from "@butler/domain/knowledge/project-knowledge.js"
import { updateProjectState } from "./project-state.js"
import { resolveWechatAllowedToolNames } from "./wechat-tool-allowlist.js"
import { resolveToolNamesForIntake, isDevWorkIntent } from "./wechat-tool-profile.js"
import { enrichDevRunResult } from "./dev-quality-gate.js"
import { classifyWechatIntentWithLlm } from "./wechat-intake-llm.js"
import type { McpToolBundle } from "./mcp-bootstrap.js"
import type { Wiring } from "./wiring.js"

export type WechatIntentKind =
  | "chat"
  | "dev_task"
  | "dev_session"
  | "switch_project"
  | "continue_dev"

export type WechatIntent = {
  readonly kind: WechatIntentKind
  readonly goal?: string
  readonly switchTarget?: string
}

const DEV_TASK_RE =
  /(?:write_file|run_command|实现|开发|编写|修改|修复|重构|添加|新增|删除|创建|写个|写入|写\s|做个|加个|改一下|帮我改|帮我写|修一下|fix|implement|refactor|add feature|bug)/iu

const CONTINUE_DEV_RE =
  /(?:继续|接着|刚才|上次|接着做|继续做|continue|resume)/iu

/** Short phrases that must stay chat (no dev_task / tool bias). */
const CHAT_ONLY_RE =
  /^(?:ping|pong|hi|hello|hey|你好|您好|在吗|在不在|几点了?|现在几点|几点钟|status|pwd|whoami)$/iu

const CHAT_COMMAND_RE =
  /^(?:运行?\s*)?(?:pwd|whoami|ping)\s*(?:命令|一下)?$/iu

function trimmed(content: string): string {
  return content.trim()
}

export function classifyWechatIntent(content: string): WechatIntent {
  const t = trimmed(content)
  if (!t) return { kind: "chat" }

  if (CHAT_ONLY_RE.test(t) || (t.length <= 24 && CHAT_COMMAND_RE.test(t))) {
    return { kind: "chat" }
  }

  if (isDevSessionPhrase(t)) {
    return { kind: "dev_session" }
  }

  const switchCmd = normalizeWechatSwitchCommand(t)
  if (switchCmd?.startsWith("/切换 ")) {
    const target = switchCmd.slice("/切换 ".length).trim()
    if (target) return { kind: "switch_project", switchTarget: target }
  }

  if (CONTINUE_DEV_RE.test(t) && t.length < 80) {
    return { kind: "continue_dev", goal: t }
  }

  if (DEV_TASK_RE.test(t)) {
    return { kind: "dev_task", goal: t }
  }

  return { kind: "chat" }
}

function doneResult(
  reply: string,
  traces: readonly string[],
  finalDecision: ButlerLoopResult["finalDecision"] = "Respond",
): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision,
    traces: [...traces],
  }
}

const DELEGATE_ASYNC_NOTICE =
  "（子代理已在后台执行，完成后将微信推送含【开发验收】的结果）"

function enrichDelegateAsyncNotice(loop: ButlerLoopResult): ButlerLoopResult {
  const delegated = loop.traces.some((t) => t.startsWith("delegate_to_subagent@"))
  if (!delegated) return loop
  if (loop.reply.includes("【开发验收】") || loop.reply.includes("子代理已在后台")) {
    return loop
  }
  const body = loop.reply.trim()
  return {
    ...loop,
    reply: body ? `${body}\n\n${DELEGATE_ASYNC_NOTICE}` : DELEGATE_ASYNC_NOTICE,
    traces: [...loop.traces, "intake:delegate-async-notice"],
  }
}

function switchProjectReply(args: {
  readonly projectId: string
  readonly env: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): string {
  const catalog = parseWechatProjectCatalog(args.env)
  const label = catalog.find((item) => item.id === args.projectId)?.label ?? args.projectId
  const pkStoreId = resolveProjectKnowledgeInboundProjectId(args.projectId, args.env)
  const tools = summarizeWechatToolProfile({
    projectId: args.projectId,
    env: args.env,
    mcpBundle: args.mcpBundle,
  })
  return [
    `已切换到项目：${args.projectId}（${label}）`,
    `知识库：${pkStoreId} · 工具：${tools.label}`,
    "后续消息使用新会话。发送 /项目概况 或 /状态 查看详情。",
  ].join("\n")
}

export type WechatIntakeLoopOptions = {
  readonly goal?: string
  /** Main Loop exposes write/run (legacy direct-exec only). */
  readonly includeExecTools: boolean
  /** Dev session grant + project WIP for dev_task / continue_dev / dev_session. */
  readonly requiresDevSession: boolean
  readonly allowedToolNames: readonly string[]
  readonly traces: readonly string[]
}

export function resolveIntakeLoopOptions(args: {
  readonly intent: WechatIntent
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): WechatIntakeLoopOptions {
  const env = args.env ?? process.env
  const baseAllowlist = resolveWechatAllowedToolNames({
    projectId: args.projectId,
    env,
    mcpBundle: args.mcpBundle,
  })
  const isDevWork = isDevWorkIntent(args.intent.kind)
  const allowedToolNames = resolveToolNamesForIntake({
    intentKind: args.intent.kind,
    baseAllowlist,
    env,
  })
  const includeExecTools = allowedToolNames.some(
    (name) => name === "write_file" || name === "run_command",
  )
  const requiresDevSession =
    isDevWork || args.intent.kind === "dev_session" || args.intent.kind === "continue_dev"
  return {
    ...(args.intent.goal ? { goal: args.intent.goal } : {}),
    includeExecTools,
    requiresDevSession,
    allowedToolNames,
    traces: [`intake:${args.intent.kind}`],
  }
}

/**
 * Route inbound after slash commands and inline approval.
 * Returns null when the caller should fall through to the default loop.
 */
export async function routeWechatIntake(args: {
  readonly wiring: Wiring
  readonly conversationId: string
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
  readonly idempotencyKey?: string
  readonly runTrigger?: RunTrigger
  readonly env?: NodeJS.ProcessEnv
  readonly mcpBundle?: McpToolBundle
}): Promise<ButlerLoopResult> {
  const env = args.env ?? process.env
  const ruleIntent = classifyWechatIntent(args.content)
  const classified = await classifyWechatIntentWithLlm({
    content: args.content,
    fallback: ruleIntent,
    env,
  })
  const intent = classified.intent

  if (intent.kind === "dev_session") {
    const session = await ensureDevSessionGrants({
      store: args.wiring.runtimeStore,
      subject: args.fromUserId,
      env,
    })
    return doneResult(formatDevSessionEnabledReply(session), ["intake:dev_session"])
  }

  if (intent.kind === "switch_project" && intent.switchTarget) {
    const projectId = resolveWechatProjectAlias(intent.switchTarget, env)
    if (!projectId) {
      return doneResult(
        `未知项目「${intent.switchTarget}」。发送 /项目 查看列表。`,
        [`intake:switch_unknown:${intent.switchTarget}`],
        "Finish",
      )
    }
    setWechatActiveProjectId(args.fromUserId, projectId, env)
    return doneResult(
      switchProjectReply({ projectId, env, mcpBundle: args.mcpBundle }),
      [`intake:switch:${projectId}`],
    )
  }

  const loopOpts = resolveIntakeLoopOptions({
    intent,
    projectId: args.projectId,
    env,
    mcpBundle: args.mcpBundle,
  })
  const intakeTraces = [
    `intake:${intent.kind}`,
    `intake-source:${classified.source}`,
    ...loopOpts.traces.filter((t) => !t.startsWith("intake:")),
  ]

  if (loopOpts.requiresDevSession) {
    await ensureDevSessionGrants({
      store: args.wiring.runtimeStore,
      subject: args.fromUserId,
      env,
    })
    updateProjectState({
      userId: args.fromUserId,
      projectId: args.projectId,
      patch: { wipSummary: args.content.trim().slice(0, 200) },
      env,
    })
  }

  const activeProject = getWechatActiveProjectId(args.fromUserId, env)
  const intakeRunTrigger: RunTrigger =
    args.runTrigger ??
    buildWechatRunTrigger({
      userId: args.fromUserId,
      conversationId: args.conversationId,
      content: args.content,
      ...(args.idempotencyKey ? { messageId: args.idempotencyKey } : {}),
      ...(loopOpts.requiresDevSession
        ? { extraPayload: { workingSetMode: "dev" as const } }
        : {}),
    })
  if (loopOpts.requiresDevSession) {
    intakeTraces.push("working-set:dev")
  }
  const loopResult = enrichDelegateAsyncNotice(
    await runButlerLoop({
      wiring: args.wiring,
      conversationId: args.conversationId,
      content: args.content,
      fromUserId: args.fromUserId,
      projectId: activeProject,
      ...(args.idempotencyKey ? { idempotencyKey: args.idempotencyKey } : {}),
      runTrigger: intakeRunTrigger,
      allowedToolNames: loopOpts.allowedToolNames,
      ...(loopOpts.goal ? { goal: loopOpts.goal } : {}),
      env,
    }),
  )

  const enriched = await enrichDevRunResult({
    projectId: activeProject,
    fromUserId: args.fromUserId,
    includeExecTools: loopOpts.includeExecTools,
    loop: loopResult,
    env,
    runtimeStore: args.wiring.runtimeStore,
  })

  return {
    ...enriched,
    traces: [...intakeTraces, ...enriched.traces],
  }
}

/** When true, routes non-slash inbound through intake (default on). */
export function isWechatIntakeEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw = (env["BUTLER_V5_INTAKE_ENABLED"] ?? "1").trim().toLowerCase()
  return raw !== "0" && raw !== "false" && raw !== "off"
}
