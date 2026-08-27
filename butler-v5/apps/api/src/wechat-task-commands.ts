import { createTaskRecord } from "@butler/domain/knowledge/task-procedure.js"
import { getWechatActiveProjectId } from "./wechat-active-project.js"
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
    const items = await store.listBySubject({ subject, status: "open", limit: 50 })
    const scoped = items.filter((item) => matchesActiveProject(item.title, active))
    if (scoped.length === 0) {
      return done(
        `当前项目「${active}」没有 open 待办。\n用法：/待办 新增 <标题> [| <目标>]`,
        ["wechat-task: empty list"],
      )
    }
    const lines = [`待办（${active}）:`]
    for (const item of scoped) {
      lines.push(
        `• ${shortId(item.id)} ${stripProjectPrefix(item.title, active)}${item.goal ? `\n  目标: ${item.goal.slice(0, 80)}` : ""}`,
      )
    }
    lines.push("", "命令：/运行 <id> · /完成 <id>")
    return done(lines.join("\n"), ["wechat-task: list"])
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
        [
          `待办 ${shortId(match.id)} 已在后台运行。`,
          "完成后会主动推送微信（BUTLER_V5_RUN_NOTIFY_ENABLED=1）。",
          "同步运行：设置 BUTLER_V5_TASK_RUN_ASYNC=0 且 BUTLER_V5_RUN_NOTIFY_ENABLED=0。",
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
          `决策：${result.loop.finalDecision}`,
          result.loop.reply,
        ].join("\n\n"),
        iterations: result.loop.iterations,
        toolCalls: result.loop.toolCalls,
        finalDecision: result.loop.finalDecision,
        traces: [`wechat-task: run ${match.id}`, ...result.loop.traces],
      }
    } catch (err) {
      return done(
        `运行失败：${err instanceof Error ? err.message : String(err)}`,
        [`wechat-task: run error ${match.id}`],
      )
    }
  }

  if (trimmed.startsWith("/完成")) {
    const token = trimmed.slice("/完成".length).trim()
    if (!token) {
      return done("用法：/完成 <待办id前缀>", ["wechat-task: done usage"])
    }
    const match = await resolveTaskByToken(args.wiring, subject, token)
    if (!match) {
      return done(`未找到待办「${token}」。`, ["wechat-task: done not found"])
    }
    const existing = await store.get(match.id)
    if (!existing) {
      return done(`未找到待办「${token}」。`, ["wechat-task: done missing"])
    }
    await store.update({ ...existing, status: "done", updatedAt: Date.now() })
    return done(`待办 ${shortId(match.id)} 已标记完成。`, [`wechat-task: done ${match.id}`])
  }

  return null
}
