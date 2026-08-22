import { Effect } from "effect"
import { pickLLMProvider, type LLMMessage } from "@butler/adapters"
import { isSubagentEnabled } from "./subagent-config.js"

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
 * emit one of the `ModelDecision` JSON shapes (Respond / CallTool /
 * Finish / AskApproval / Delegate) instead of free-form text. Tools
 * are passed for the LLM's awareness but the loop drives tool
 * execution itself; this keeps the contract simple and lets the
 * loop log every decision for the operator trace.
 */
export function buildWechatInboundMessages(
  content: string,
  env: NodeJS.ProcessEnv = process.env,
): readonly LLMMessage[] {
  const decisionShapes = [
    '- {"_tag":"Respond","content":"<your reply text>"}  — final answer to the user',
    '- {"_tag":"CallTool","toolName":"<tool>","args":{...}}  — request a tool call (loop will run it and feed the result back)',
    ...(isSubagentEnabled(env)
      ? [
          '- {"_tag":"Delegate","role":"<role>","task":"<task>"}  — hand the task off to a subagent (runs in background; you may then Respond or CallTool again)',
        ]
      : []),
    '- {"_tag":"Finish","reason":"<short reason>"}  — task done, no reply needed',
    '- {"_tag":"AskApproval","question":"<the question>"}  — need user confirmation',
  ]

  const toolLines = [
    "- recall_history(limit?: number): recent conversation events",
    "- get_current_time(): current time in Asia/Shanghai (UTC+8), formatted in Chinese",
    "- greet_with_time(): a Chinese greeting based on the current time of day",
    "- summarize_today(): 24-hour activity summary for this conversation, broken down by event type",
    "- read_file(path): read a UTF-8 text file inside the workspace (max 64KiB; path cannot escape the root)",
    "- run_command(argv): run an allowlisted command with no shell (cat/date/echo/git/grep/head/ls/node/pnpm/pwd/python3/rg/wc); args cannot contain '..' or start with '/'",
    "- send_wechat_file(path, caption?): send a workspace image or file to the current WeChat user",
    ...(isSubagentEnabled(env)
      ? [
          "- delegate_to_subagent(task, role?, capabilities?): delegate a task to a subagent (runs in background, returns later). Use when the user's request requires capabilities you don't have. Optional `capabilities` is an array of strings from the allowlist (general, get_current_time, summarize_today, recall_history, read_file, run_command); defaults to ['general'] if unspecified.",
        ]
      : []),
  ]

  const closing = isSubagentEnabled(env)
    ? "If the user just wants a reply, use Respond. If you need data the tools provide, use CallTool and wait for the tool result. Use Delegate when the work should happen asynchronously in a child agent and you want to keep replying to the user."
    : "If the user just wants a reply, use Respond. If you need data the tools provide, use CallTool and wait for the tool result."

  return [
    {
      role: "system",
      content: [
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
