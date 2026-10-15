import { type LLMMessage } from "@butler/adapters"
import { shouldAdvertiseDelegate } from "./wechat-tool-profile.js"

// D82 T3: `generateLLMReply` (and with it the LLM_TIMEOUT / LLMReplyLogger /
// defaultLogger surface and the `pickLLMProvider` import) was deleted as dead
// code. Nothing in the production path called it — the loop is driven by
// runButlerLoop in wechat-inbound-butler.ts, which resolves its adapter via
// pickLLMForRole(env, "plan") in the composition root. Keeping a second,
// role-unaware provider picker alive was the trap: it does not know about the
// MiniMax provider and does not honour the fixture override, so anyone
// changing providers would have "fixed" a function nothing calls.

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
  // D82 T3: single source of truth for the tag names used in this prompt.
  // They must match the tags `decodeDecision` accepts (packages/runtime/
  // decision.ts). They used to be spelled out separately in `decisionShapes`
  // and again in prose (`closing`), where the prose said "CallTool" and
  // "Delegate" — neither of which is a real tag. A real LLM took the prose
  // literally, emitted `{"_tag":"Delegate"}`, and decodeDecision rejected it
  // (the D81 decode bug). Everything below now interpolates these constants.
  const RESPOND_TAG = "Respond"
  const CALL_TAG = "CallCapability"
  const DELEGATE_TAG = "StartChildRun"
  const decisionShapes = [
    `- {"_tag":"${RESPOND_TAG}","content":"<your reply text>"}  — final answer to the user`,
    `- {"_tag":"${CALL_TAG}","name":"<capability>","arguments":{...},"callId":"<optional>"}  — request a Capability invocation (loop will run it and feed the result back)`,
    ...(advertiseDelegate
      ? [
          `- {"_tag":"${DELEGATE_TAG}","role":"<role>","objective":"<objective>","grants":[]}  — hand the task off to a subagent (runs in background; you may then ${RESPOND_TAG} or ${CALL_TAG} again)`,
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
            : "- delegate_to_subagent(task, role?, capabilities?): delegate coding or shell work to a subagent (async). Prefer StartChildRun over direct write/run when the user asks to implement or change code.",
        ]
      : []),
  ]

  // D82 T3: the tags named here are interpolated from the same constants
  // `decisionShapes` is declared with, so the two cannot drift apart.
  const closing = advertiseDelegate
    ? includeExecTools
      ? `If the user just wants a reply, use ${RESPOND_TAG}. If you need data the tools provide, use ${CALL_TAG} (with the tool's name) and wait for the tool result. Use ${DELEGATE_TAG} when the work should happen asynchronously in a child agent and you want to keep replying to the user.`
      : `If the user just wants a reply, use ${RESPOND_TAG}. For development tasks (write files, run commands), use ${DELEGATE_TAG} to hand off to the exec subagent instead of ${CALL_TAG} for run_command/write_file.`
    : includeExecTools
      ? `If the user just wants a reply, use ${RESPOND_TAG}. For write_file or run_command, use ${CALL_TAG} directly (dev session is active — no need to delegate).`
      : `If the user just wants a reply, use ${RESPOND_TAG}. Read-only tools are available; development writes/commands require dev session or explicit approval.`

  // P2 fix 2026-09-04: inject owner / project context so the model
  // answers "v5 有什么问题" with v5-specific context rather than asking
  // "v5 是什么" (B1 gap surfaced in real-LLM recording 5ef5ab19).
  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? "").trim()
  const contextLines: string[] = [
    "You are v5 — the butler-v5 wechat coding assistant (Effect-TS, functional arch).",
    "When the user references 'v5' or this project, it means butler-v5 (the v5 line of the wechat coding butler). Do not ask what v5 is.",
    "Reply style: WeChat is mobile. Keep replies to 1-3 short sentences by default. Use markdown sparingly (no tables wider than the screen; bullets ≤ 5 items). For complex analyses the owner can request '详细分析' to opt into a longer reply.",
    "Take-action bias: if the owner's intent is reasonably clear from one short request, proceed (call the tool) rather than ask 3+ clarifying questions. The policy-gate already enforces confirmation for write_file / mutating run_command, so do NOT pre-ask 'can I write that?' — the system will prompt the owner automatically when needed.",
    "Tool selection: prefer read_file (direct workspace path access) over run_command with shell find/ls/cat for file discovery. Use run_command only when read_file cannot address the task (e.g., package scripts, system introspection, git history).",
    "Convergence: after at most 1-2 file-discovery calls (read_file or bounded find), commit to a concrete plan or ask 1 clarifying question — do not iterate further on inspection alone. The owner wants forward motion.",
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
        `Available tools (to run one, emit a ${CALL_TAG} whose "name" is exactly the tool name below):`,
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
export function stubReply(_content: string, _fromUserId: string, _projectId: string): string {
  // D60 T2.1 (audit #3 F-02): drop raw fromUserId + raw projectId +
  // 'MVP stub reply' jargon (3x D48 §4 violation). Owner just needs
  // confirmation the message was received and is being processed.
  return "已收到，正在处理中。"
}
