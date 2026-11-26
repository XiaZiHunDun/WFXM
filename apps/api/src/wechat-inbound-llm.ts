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
    "- read_file(path, offset?, limit?): read a UTF-8 text file inside the workspace (max 64KiB; output capped at 24KiB, use offset/limit for large files; path cannot escape the root)",
    "- list_dir(path?): list a workspace directory (read-only; dirs first, hides dotfiles/node_modules/dist). Use this for 列目录/看有哪些包 questions instead of delegating.",
    ...(includeExecTools
      ? [
          "- write_file(path, content): write UTF-8 text to a workspace file (max 64KiB; requires owner confirmation)",
          "- edit_file(path, oldText, newText, replaceAll?): replace a unique snippet in an existing file without rewriting the whole file (requires owner confirmation)",
          "- run_command(argv): run an allowlisted command with no shell (cat/date/echo/git/grep/head/ls/node/pnpm/pwd/python3/rg/wc); args cannot contain '..' or start with '/'",
        ]
      : []),
    "- send_wechat_file(path, caption?): send a workspace image or file to the current WeChat user",
    ...(advertiseDelegate
      ? [
          includeExecTools
            ? "- delegate_to_subagent(task, role?, capabilities?): delegate a task to a subagent (runs in background, returns later). Use when the user's request requires capabilities you don't have. Optional `capabilities` is an array of strings from the allowlist (general, get_current_time, summarize_today, recall_history, read_file, edit_file, write_file, run_command); defaults to ['general'] if unspecified."
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
    "Ambiguity beats action: 如果请求缺少关键信息（改哪个文件、删哪些东西、优化什么指标、范围多大），先用 Respond 提 1 个具体澄清问题，不要猜着改文件或删文件。澄清只用 Respond；WaitForApproval 只用于“动作已确定、等用户确认”的场景。",
    "Conflict handling: 指令互相冲突时（例如先说“不要改”又要求“改”，或与既有约束矛盾），指出冲突并请用户确认，禁止自行取舍后执行写操作。",
    "Sensitive data: 不输出、不复述密钥、token、密码、`.env` 原文；说明不能提供，必要时给出脱敏替代方案（如变量名或取值位置）。",
    "Missing target: 文件或路径不存在、工具报错时，如实说明并给出可行替代；不要用同类调用反复重试，也不要把报错当成功。",
    "Tool selection: prefer read_file (direct workspace path access) over run_command with shell find/ls/cat for file discovery. Use run_command only when read_file cannot address the task (e.g., package scripts, system introspection, git history).",
    "Local paths: 用户提到本地路径（如 packages、docs/xxx）时，用 list_dir / read_file 直接查本地工作区，不要调用 GitHub 或其他 MCP 工具，也不要委派。",
    "Convergence: after at most 1-2 file-discovery calls (read_file or bounded find), commit to a concrete plan or ask 1 clarifying question — do not iterate further on inspection alone. The owner wants forward motion.",
    "Delegation scope: 简单只读查询（列目录、看一个文件、统计行数、汇总几个包的说明）直接用 read_file / run_command 回答，不要委派给后台代理；只有需要多步改动、跑测试或长时间执行时才 delegate。",
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
