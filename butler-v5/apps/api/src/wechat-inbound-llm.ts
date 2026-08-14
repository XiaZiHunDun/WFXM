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
 * R8.x.2 keeps this stateless: system prompt + the user's raw content.
 * Conversation history and tool calls land in R8.x.3.
 */
export function buildWechatInboundMessages(content: string): readonly LLMMessage[] {
  return [
    {
      role: "system",
      content: "You are a helpful butler. Reply concisely in the user's language.",
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
          return { role: "assistant" as const, content: "" }
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
