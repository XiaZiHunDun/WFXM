import { Effect } from "effect"
import { pickLLMProvider, type LLMMessage } from "@butler/adapters"
import { shouldAdvertiseDelegate } from "./wechat-tool-profile.js"

/**
 * How long to wait for a real LLM response before falling back to the
 * stub reply. Keeps the v5 inbound route from hanging if a provider
 * is slow or unreachable.
 */
const LLM_TIMEOUT = "10 seconds" as const

/**
 * Minimal logger surface — clean separation lets tests inject a
 * silent logger and production code use stderr. Avoids the project
 * no-console ESLint rule by going through a typed function.
 */
export interface LLMReplyLogger {
  error: (message: string, error: unknown) => void
}

const defaultLogger: LLMReplyLogger = {
  error: (message, error) => {
    // eslint-disable-next-line no-console -- intentional stderr log for operator debugging
    console.error(message, error)
  },
}

/**
 * Build the minimal messages array for a wechat inbound turn.
 * R8.x.3: the butler loop runs an AgentKernel + decodeDecision over
 * the model output, so the system prompt now instructs the model to
 * emit one of the `ModelDecision` JSON shapes (DESIGN §6.2: Respond /
 * CallCapability / StartChildRun / WaitForApproval / Finish) instead of
 * free-form text. Tools are passed for the LLM's awareness but the loop
 * drives tool execution itself; this keeps the contract simple and lets
 * the loop log every decision for the operator trace.
 */
export function buildWechatInboundMessages(
  content: string,
  env: NodeJS.ProcessEnv = process.env,
  opts: { readonly includeExecTools?: boolean; readonly fromUserId?: string } = {},
): readonly LLMMessage[] {
  const includeExecTools = opts.includeExecTools ?? false
  const fromUserId = opts.fromUserId
  const advertiseDelegate = shouldAdvertiseDelegate({ includeExecTools, env })
  const decisionShapes = [
    '- {"_tag":"Respond","content":"<your reply text>"}  — final answer to the user',
    '- {"_tag":"CallCapability","name":"<capability>","arguments":{...},"callId":"<optional>"}  — request a Capability invocation (loop will run it and feed the result back)',
    ...(advertiseDelegate
      ? [
          '- {"_tag":"StartChildRun","role":"<role>","objective":"<objective>","grants":[]}  — hand the task off to a subagent (runs in background; you may then Respond or CallCapability again)',
        ]
      : []),
    '- {"_tag":"Finish","reason":"<short reason>"}  — task done, no reply needed',
    '- {"_tag":"WaitForApproval","question":"<the question>"}  — need user confirmation',
  ]

  const toolLines = [
    "- recall_history(limit?: number): recent conversation events",
    "- get_current_time(): current time in Asia/Shanghai (UTC+8), formatted in Chinese",
    "- greet_with_time(): a Chinese greeting based on the current time of day",
    "- summarize_today(): 24-hour activity summary for this conversation, broken down by event type",
    "- read_file(path): read a UTF-8 text file inside the workspace (max 64KiB; path cannot escape the root)",
    ...(includeExecTools
      ? [
          "- write_file(path, content): write UTF-8 text to a workspace file (max 64KiB; requires owner confirmation)",
          "- run_command(argv): run an allowlisted command with no shell (cat/date/echo/git/grep/head/ls/node/pnpm/pwd/python3/rg/wc); args cannot contain '..' or start with '/'",
        ]
      : []),
    "- send_wechat_file(path, caption?): send a workspace image or file to the current WeChat user",
    ...(advertiseDelegate
      ? [
          includeExecTools
            ? "- delegate_to_subagent(task, role?, capabilities?): delegate a task to a subagent (runs in background, returns later). Use when the user's request requires capabilities you don't have. Optional `capabilities` is an array of strings from the allowlist (general, get_current_time, summarize_today, recall_history, read_file, write_file, run_command); defaults to ['general'] if unspecified."
            : "- delegate_to_subagent(task, role?, capabilities?): delegate coding or shell work to a subagent (async). Prefer Delegate over direct write/run when the user asks to implement or change code.",
        ]
      : []),
  ]

  const closing = advertiseDelegate
    ? includeExecTools
      ? "If the user just wants a reply, use Respond. If you need data the tools provide, use CallTool and wait for the tool result. Use Delegate when the work should happen asynchronously in a child agent and you want to keep replying to the user."
      : "If the user just wants a reply, use Respond. For development tasks (write files, run commands), use Delegate to hand off to the exec subagent instead of CallTool for run_command/write_file."
    : includeExecTools
      ? "If the user just wants a reply, use Respond. For write_file or run_command, use CallTool directly (dev session is active — no need to delegate)."
      : "If the user just wants a reply, use Respond. Read-only tools are available; development writes/commands require dev session or explicit approval."

  // P2 fix 2026-09-04: inject owner / project context so the model
  // answers "v5 有什么问题" with v5-specific context rather than asking
  // "v5 是什么" (B1 gap surfaced in real-LLM recording 5ef5ab19).
  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? "").trim()
  const contextLines: string[] = [
    "You are v5 — the butler-v5 wechat coding assistant (Effect-TS, functional arch).",
    "When the user references 'v5' or this project, it means butler-v5 (the v5 line of the wechat coding butler). Do not ask what v5 is.",
    "Reply style: WeChat is mobile. Keep replies to 1-3 short sentences by default. Use markdown sparingly (no tables wider than the screen; bullets ≤ 5 items). For complex analyses the owner can request '详细分析' to opt into a longer reply.",
    "Take-action bias: if the owner's intent is reasonably clear from one short request, proceed (call the tool) rather than ask 3+ clarifying questions. The policy-gate already enforces confirmation for write_file / mutating run_command, so do NOT pre-ask 'can I write that?' — the system will prompt the owner automatically when needed.",
  ]
  if (workspaceRoot) {
    contextLines.push(
      `Workspace root: ${workspaceRoot} (pnpm monorepo: packages/{domain,ports,adapters,runtime,persistence} + apps/api + apps/cli).`,
    )
  }
  if (fromUserId) {
    contextLines.push(`Current owner: ${fromUserId}.`)
  }

  return [
    {
      role: "system",
      content: [
        ...contextLines,
        "",
        "You are a helpful butler for a Chinese-language user.",
        "Current time is always interpreted in Asia/Shanghai (UTC+8 / 北京时间 / 中国标准时间).",
        "Reply naturally in Chinese; do not switch back to UTC.",
        "",
        "Return exactly one JSON object (no prose, no markdown fence) using one of these shapes:",
        ...decisionShapes,
        "",
        "Available tools (use the CallTool shape when you need them):",
        ...toolLines,
        "",
        closing,
      ].join("\n"),
    },
    { role: "user", content },
  ]
}

/**
 * Deterministic stub reply used when no LLM key is configured OR when
 * the LLM call fails / times out. Keeps the v4 → v5 → v4 contract intact
 * (the user always gets a `reply` field back).
 */
export function stubReply(content: string, fromUserId: string, projectId: string): string {
  return `v5 received message from ${fromUserId} (project=${projectId}); v5 butler processing is async - this is the MVP stub reply`
}

/**
 * Call the configured LLM provider and return its text reply.
 * Falls back to the stub reply on any failure (missing key, network
 * error, timeout, empty content). All failure modes are logged so
 * the operator can debug without breaking the route.
 *
 * Returned text is always non-empty (either LLM reply or stub).
 */
export async function generateLLMReply(args: {
  readonly content: string
  readonly fromUserId: string
  readonly projectId: string
  readonly env?: NodeJS.ProcessEnv
  readonly logger?: LLMReplyLogger
}): Promise<string> {
  const env = args.env ?? process.env
  const logger = args.logger ?? defaultLogger
  const adapter = pickLLMProvider(env)
  if (!adapter) {
    return stubReply(args.content, args.fromUserId, args.projectId)
  }

  const messages = buildWechatInboundMessages(args.content)

  const outcome = await Effect.runPromise(
    adapter.complete(messages).pipe(
      Effect.timeout(LLM_TIMEOUT),
      Effect.match({
        onFailure: (err) => {
          logger.error(
            `[v5-wechat-inbound] LLM call failed (fromUserId=${args.fromUserId}); falling back to stub:`,
            err,
          )
          // R8.x.4: adapter.complete now returns LLMAssistantResponse
          // (content + toolCalls + stopReason). Return an empty response
          // shape on failure so the route can fall back to the stub
          // reply without breaking the typecheck.
          return { content: "", toolCalls: [], stopReason: "stop" as const }
        },
        onSuccess: (msg) => msg,
      }),
    ),
  )

  const text = outcome.content.trim()
  if (!text) {
    return stubReply(args.content, args.fromUserId, args.projectId)
  }
  return text
}
