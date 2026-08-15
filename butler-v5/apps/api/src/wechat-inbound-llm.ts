import { Effect } from "effect"
import { pickLLMProvider, type LLMMessage } from "@butler/adapters"

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
export function buildWechatInboundMessages(content: string): readonly LLMMessage[] {
  return [
    {
      role: "system",
      content: [
        "You are a helpful butler. Reply concisely in the user's language.",
        "",
        "Return exactly one JSON object (no prose, no markdown fence) using one of these shapes:",
        '- {"_tag":"Respond","content":"<your reply text>"}  — final answer to the user',
        '- {"_tag":"CallTool","toolName":"<tool>","args":{...}}  — request a tool call (loop will run it and feed the result back)',
        '- {"_tag":"Finish","reason":"<short reason>"}  — task done, no reply needed',
        '- {"_tag":"AskApproval","question":"<the question>"}  — need user confirmation',
        "",
        "Available tools (use the CallTool shape when you need them):",
        "- recall_history(limit?: number): recent conversation events",
        "- get_current_time(): current server time as ISO 8601",
        "",
        "If the user just wants a reply, use Respond. If you need data the tools provide, use CallTool and wait for the tool result.",
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
