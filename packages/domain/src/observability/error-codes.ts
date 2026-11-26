/**
 * Phase 5 P0: stable error-code registry for failure envelopes.
 *
 * User-facing replies must never surface raw exception text / stacks /
 * internal ids. The reply carries only a stable code plus the first 8
 * characters of the turn id so the Owner can correlate the report with
 * the persisted trace (`GET /v1/owner/traces?turnId=...`).
 */

export type TraceErrorCode =
  | "E-LLM-01"
  | "E-CTX-01"
  | "E-TOOL-01"
  | "E-POL-01"
  | "E-RUN-01"
  | "E-DB-01"
  | "E-REQ-01"
  | "E-INT-01"

export interface ErrorCodeInfo {
  readonly code: TraceErrorCode
  readonly title: string
  /** Whether the caller can reasonably retry the same request. */
  readonly retryable: boolean
  /** Short owner-facing hint (never a raw exception string). */
  readonly ownerHint: string
}

export const UNKNOWN_ERROR_CODE: TraceErrorCode = "E-INT-01"

export const ERROR_CODES: Readonly<Record<TraceErrorCode, ErrorCodeInfo>> = {
  "E-LLM-01": {
    code: "E-LLM-01",
    title: "模型调用失败",
    retryable: true,
    ownerHint: "模型服务暂时不可用，请稍后再试。",
  },
  "E-CTX-01": {
    code: "E-CTX-01",
    title: "上下文超限",
    retryable: false,
    ownerHint: "本轮上下文过长，请精简后重新发送。",
  },
  "E-TOOL-01": {
    code: "E-TOOL-01",
    title: "工具执行失败",
    retryable: true,
    ownerHint: "工具执行没有完成，请稍后再试。",
  },
  "E-POL-01": {
    code: "E-POL-01",
    title: "策略或审批拒绝",
    retryable: false,
    ownerHint: "该操作被策略拦截或审批未通过。",
  },
  "E-RUN-01": {
    code: "E-RUN-01",
    title: "运行状态冲突",
    retryable: true,
    ownerHint: "当前对话还有未完成的请求，请稍后再发。",
  },
  "E-DB-01": {
    code: "E-DB-01",
    title: "持久化失败",
    retryable: true,
    ownerHint: "后台存储暂时不可用，请稍后再试。",
  },
  "E-REQ-01": {
    code: "E-REQ-01",
    title: "请求非法",
    retryable: false,
    ownerHint: "请求内容不合法，请检查后重新发送。",
  },
  "E-INT-01": {
    code: "E-INT-01",
    title: "内部错误",
    retryable: true,
    ownerHint: "处理过程中出现未知错误，请稍后再试。",
  },
}

/** Error `_tag` / constructor-name → code. Exact matches win over keywords. */
const TAG_CODE_MAP: Readonly<Record<string, TraceErrorCode>> = {
  LLMUnavailable: "E-LLM-01",
  ContextOverflow: "E-CTX-01",
  ToolFailed: "E-TOOL-01",
  GuardRejected: "E-POL-01",
  ApprovalDenied: "E-POL-01",
  ApprovalRejected: "E-POL-01",
  ActiveMainRunConflict: "E-RUN-01",
  CompletedMainRunReplay: "E-RUN-01",
  PersistenceFailed: "E-DB-01",
  InvalidRequest: "E-REQ-01",
  InvalidRunTrigger: "E-REQ-01",
}

/** Ordered keyword fallbacks; first match wins. */
const KEYWORD_RULES: readonly { readonly code: TraceErrorCode; readonly pattern: RegExp }[] = [
  {
    code: "E-CTX-01",
    pattern:
      /(context length|context window|context_length|maximum context|too many tokens|token limit|prompt is too long)/i,
  },
  {
    code: "E-DB-01",
    pattern:
      /(database|postgres|pglite|persistence failed|persist failed|sql error|deadlock|relation .* does not exist)/i,
  },
  {
    code: "E-POL-01",
    pattern: /(policy|approval|not allowed|denied|forbidden|guard rejected)/i,
  },
  {
    code: "E-RUN-01",
    pattern:
      /(run conflict|active (main )?run|already completed|invalid run state|state transition)/i,
  },
  {
    code: "E-REQ-01",
    pattern: /(invalid (request|body|trigger)|validation failed|bad request)/i,
  },
  {
    code: "E-TOOL-01",
    pattern: /(tool .*fail|tool call failed|capability .*fail|tool execution)/i,
  },
  {
    code: "E-LLM-01",
    pattern:
      /(llm|model call|openai|anthropic|deepseek|fetch failed|econnrefused|etimedout|timeout|network|socket hang up)/i,
  },
]

function readTag(err: unknown): string | null {
  if (!err || typeof err !== "object") return null
  const tag = (err as { readonly _tag?: unknown })._tag
  return typeof tag === "string" && tag.trim() !== "" ? tag.trim() : null
}

function readConstructorName(err: unknown): string | null {
  if (!(err instanceof Error)) return null
  const ctorName = err.constructor?.name?.trim()
  if (ctorName && ctorName !== "Error") return ctorName
  const name = err.name?.trim()
  return name ? name : null
}

function readMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === "string") return err
  return ""
}

/**
 * Map any thrown value to a stable error code. Unknown shapes fall back
 * to `E-INT-01` — callers must never surface the raw value to the user.
 */
export function resolveErrorCode(err: unknown): TraceErrorCode {
  const tag = readTag(err)
  if (tag !== null && TAG_CODE_MAP[tag] !== undefined) return TAG_CODE_MAP[tag]

  const ctor = readConstructorName(err)
  if (ctor !== null && TAG_CODE_MAP[ctor] !== undefined) return TAG_CODE_MAP[ctor]

  const text = `${tag ?? ""} ${ctor ?? ""} ${readMessage(err)}`
  for (const rule of KEYWORD_RULES) {
    if (rule.pattern.test(text)) return rule.code
  }
  return UNKNOWN_ERROR_CODE
}

/** First 8 characters of the turn id (literal, not a hash). */
export function turnIdShort(turnId: string | null | undefined): string {
  if (typeof turnId !== "string") return ""
  const trimmed = turnId.trim()
  return trimmed.length <= 8 ? trimmed : trimmed.slice(0, 8)
}

/**
 * Owner-visible failure envelope: stable code + truncated turn id, then a
 * fixed recovery hint. No raw exception text / stack / internal UUID.
 */
export function formatFailureEnvelope(input: {
  readonly code: TraceErrorCode
  readonly turnId?: string | null
}): string {
  const short = turnIdShort(input.turnId)
  const prefix = short === "" ? `[${input.code}]` : `[${input.code} · ${short}]`
  // Phase 7 fix F9: a failed parent turn may have already delegated work
  // that is still running in the subagent outbox. Say so explicitly instead
  // of leaving the owner to assume nothing happened.
  return `${prefix} 处理失败，已记录。请稍后再发一次；若反复出现，请把这条信息发给管理员。\n（若本轮已派出子任务，它们可能仍在后台执行，完成后会单独汇报。）`
}
