import { createTaskRecord } from "@butler/domain/knowledge/task-procedure.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
import { formatDecision, resolveProjectLabel } from "./owner-jargon.js"
import { safeOwnerError } from "./safe-owner-error.js"
import { isTaskRunAsyncEnabled, scheduleBackgroundTaskRun } from "./task-run-background.js"
import { runTaskGoal } from "./task-run.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

function taskProjectPrefix(projectId: string): string {
  return `[${projectId.trim()}] `
}

function stripProjectPrefix(title: string, projectId: string): string {
  const prefix = taskProjectPrefix(projectId)
  return title.startsWith(prefix) ? title.slice(prefix.length) : title
}

function matchesActiveProject(title: string, activeProjectId: string): boolean {
  return title.startsWith(taskProjectPrefix(activeProjectId))
}

function done(reply: string, traces: readonly string[]): ButlerLoopResult {
  return {
    reply,
    iterations: 0,
    toolCalls: 0,
    finalDecision: "Respond",
    traces: [...traces],
  }
}

function shortId(taskId: string): string {
  return taskId.slice(0, 8)
}

/**
 * Pure digest for the open-tasks segment (used by `/待办` and the combined
 * `task_digest` intent handler). Returns the same text the `/待办` slash
 * command emits when `emptyMessage` is omitted, so slash output and digest
 * segment stay in lockstep. The combined digest handler passes a terse
 * `emptyMessage` so empty segments read "暂无" instead of the verbose
 * usage hint.
 */
export async function formatOpenTasksDigest(
  args: {
    readonly wiring: Wiring
    readonly fromUserId: string
    readonly env?: NodeJS.ProcessEnv
  },
  options?: { readonly emptyMessage?: string },
): Promise<{ readonly text: string; readonly isEmpty: boolean }> {
  const env = args.env ?? process.env
  const subject = args.fromUserId.trim()
  const active = getWechatActiveProjectId(subject, env)
  const store = args.wiring.taskStore
  if (!store) {
    return { text: "Task 存储不可用。", isEmpty: true }
  }
  const items = await store.listBySubject({ subject, status: "open", limit: 50 })
  const scoped = items.filter((item) => matchesActiveProject(item.title, active))
  if (scoped.length === 0) {
    return {
      text:
        options?.emptyMessage ??
        `当前项目「${resolveProjectLabel(active, env)}」没有 open 待办。\n用法：/待办 新增 <标题> [| <目标>]`,
      isEmpty: true,
    }
  }
  const lines = [`待办（${resolveProjectLabel(active, env)}）:`]
  for (const item of scoped) {
    lines.push(
      `• ${shortId(item.id)} ${stripProjectPrefix(item.title, active)}${item.goal ? `\n  目标: ${item.goal.slice(0, 80)}` : ""}`,
    )
  }
  lines.push("", "命令：/运行 <id> · /完成 <id>")
  return { text: lines.join("\n"), isEmpty: false }
}

async function resolveTaskByToken(
  wiring: Wiring,
  subject: string,
  token: string,
): Promise<{ readonly id: string; readonly title: string } | null> {
  const store = wiring.taskStore
  if (!store) return null
  const items = await store.listBySubject({ subject, limit: 100 })
  const exact = items.find((item) => item.id === token || shortId(item.id) === token)
  return exact ? { id: exact.id, title: exact.title } : null
}

export async function tryWechatTaskCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (!trimmed.startsWith("/待办") && !trimmed.startsWith("/运行") && !trimmed.startsWith("/完成")) {
    return null
  }

  const store = args.wiring.taskStore
  if (!store) {
    return done("Task 存储不可用。", ["wechat-task: no store"])
  }

  const subject = args.fromUserId.trim()
  const active = getWechatActiveProjectId(subject, env)

  if (trimmed === "/待办" || trimmed === "/tasks") {
    const digest = await formatOpenTasksDigest({
      wiring: args.wiring,
      fromUserId: args.fromUserId,
      env,
    })
    return done(digest.text, [digest.isEmpty ? "wechat-task: empty list" : "wechat-task: list"])
  }

  if (trimmed.startsWith("/待办 新增") || trimmed.startsWith("/待办 新建")) {
    const sep = trimmed.startsWith("/待办 新增") ? "/待办 新增" : "/待办 新建"
    const rest = trimmed.slice(sep.length).trim()
    if (!rest) {
      return done("用法：/待办 新增 <标题> [| <目标>]", ["wechat-task: add usage"])
    }
    const pipe = rest.indexOf("|")
    const titleRaw = (pipe >= 0 ? rest.slice(0, pipe) : rest).trim()
    const goalRaw = (pipe >= 0 ? rest.slice(pipe + 1) : titleRaw).trim()
    const created = createTaskRecord({
      subject,
      title: `${taskProjectPrefix(active)}${titleRaw}`,
      goal: goalRaw || titleRaw,
      status: "open",
    })
    if (!created.ok) {
      return done(`无法创建待办：${created.reason}`, ["wechat-task: create failed"])
    }
    const saved = await store.create(created.value)
    return done(
      `已添加待办 ${shortId(saved.id)}：${titleRaw}\n运行：/运行 ${shortId(saved.id)}`,
      [`wechat-task: created ${saved.id}`],
    )
  }

  if (trimmed.startsWith("/运行")) {
    const token = trimmed.slice("/运行".length).trim()
    if (!token) {
      return done("用法：/运行 <待办id前缀>", ["wechat-task: run usage"])
    }
    const match = await resolveTaskByToken(args.wiring, subject, token)
    if (!match) {
      return done(`未找到待办「${token}」。`, ["wechat-task: run not found"])
    }
    if (isTaskRunAsyncEnabled(env)) {
      const scheduled = scheduleBackgroundTaskRun({
        wiring: args.wiring,
        taskId: match.id,
        subject,
        title: stripProjectPrefix(match.title, active),
        env,
      })
      if (!scheduled.ok) {
        return done(scheduled.reason, [`wechat-task: run busy ${match.id}`])
      }
      return done(
        // D60 T2.3 (audit #3 F-07): drop env-var knobs from owner-facing reply.
        // Notify/sync are operator concerns not surfaced to owner.
        [
          `待办 ${shortId(match.id)} 已在后台运行。`,
          "完成后会主动推送微信。",
        ].join("\n"),
        [`wechat-task: async run ${match.id}`],
      )
    }
    try {
      const result = await runTaskGoal({
        wiring: args.wiring,
        taskId: match.id,
        env,
      })
      return {
        reply: [
          `待办 ${shortId(match.id)} 已运行。`,
          `决策：${formatDecision(result.loop.finalDecision)}`,
          result.loop.reply,
        ].join("\n\n"),
        iterations: result.loop.iterations,
        toolCalls: result.loop.toolCalls,
        finalDecision: result.loop.finalDecision,
        traces: [`wechat-task: run ${match.id}`, ...result.loop.traces],
      }
    } catch (err) {
      return done(
        safeOwnerError(err, "运行失败，请稍后重试", {
          operation: "wechat-task-run",
          taskId: match.id,
        }),
        [`wechat-task: run error ${match.id}`],
      )
    }
  }

  if (trimmed.startsWith("/完成")) {
    const rest = trimmed.slice("/完成".length).trim()
    if (!rest) {
      return done("用法：/完成 <待办id前缀> [--force]", ["wechat-task: done usage"])
    }
    // D59 T3 (audit #3 F-05): /完成 is destructive with no owner-visible
    // warning. Require an explicit confirm suffix or --force flag before
    // marking the task as done. Without the suffix, surface a confirm gate
    // so owner sees what would change. This mirrors the inline-approval
    // 确认/拒绝 pattern used elsewhere.
    const forceSuffix = /\s+(?:--force|确认)\s*$/u
    const token = rest.replace(forceSuffix, "").trim()
    const confirmed = forceSuffix.test(rest)
    if (!token) {
      return done("用法：/完成 <待办id前缀> [--force]", ["wechat-task: done usage"])
    }
    const match = await resolveTaskByToken(args.wiring, subject, token)
    if (!match) {
      return done(`未找到待办「${token}」。`, ["wechat-task: done not found"])
    }
    const existing = await store.get(match.id)
    if (!existing) {
      return done(`未找到待办「${token}」。`, ["wechat-task: done missing"])
    }
    if (!confirmed) {
      return done(
        `待办 ${shortId(match.id)} 即将标记完成。\n回复「/完成 ${shortId(match.id)} 确认」继续，或「取消」放弃。`,
        [`wechat-task: done confirm ${match.id}`],
      )
    }
    await store.update({ ...existing, status: "done", updatedAt: Date.now() })
    return done(`待办 ${shortId(match.id)} 已标记完成。`, [`wechat-task: done ${match.id}`])
  }

  return null
}
