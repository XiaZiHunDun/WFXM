/**
 * WFXM 评估驱动 — 供 agent-eval 的 wfxm adapter 以子进程调用。
 *
 * 协议：stdin 读入一个 JSON（EvalTask + adapter 注入的脚本化 LLM fixtures）
 * → stdout 最后一行输出 `__EVAL_RESULT__<json>`，内容为可观察行为 +
 * TraceEvent v0 数组。只走 acceptance harness，不调真实模型、不开真实微信。
 *
 * 注意：不从 _fixtures.ts 导入场景（该文件依赖 vitest，tsx 直跑会失败）；
 * fixture 由 adapter 以 JSON 注入，属于运行时私有装配。
 */
import { cpSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { ingestDocumentRecord } from "@butler/domain/knowledge/document-ingest.js"
import { getSharedLocalTracer } from "@butler/runtime/observability/local-tracer.js"
import { makeAcceptanceApp, sendWechatMessage } from "../../tests/acceptance/harness.js"
import {
  diffWorkspace,
  emitResult,
  resolveInsideWorkspace,
  runTests,
  seedWorkspace,
} from "./eval-utils.js"
import type { EvalTaskInput, TraceEvent } from "./task-input.js"

async function main(): Promise<void> {
  // 评测固定采样温度，避免 provider 默认值带来的跨次方差。
  process.env.BUTLER_MODEL_TEMPERATURE ??= "0"
  const task = JSON.parse(readFileSync(0, "utf8")) as EvalTaskInput
  const hint = task.runtimeHints?.wfxm
  if (!hint?.scenarioId) throw new Error(`任务 ${task.id} 缺少 runtimeHints.wfxm.scenarioId`)
  if (!task.realModel && !hint.fixtures) {
    throw new Error(`任务 ${task.id} 缺少 runtimeHints.wfxm.fixtures`)
  }

  const traceId = crypto.randomUUID()
  const runId = task.id
  const trace: TraceEvent[] = []
  let seq = 0
  let rootSpanId: string | null = null
  const push = (
    type: string,
    payload: Record<string, unknown>,
    actor: TraceEvent["actor"] = { kind: "system", id: "wfxm" },
    tsOverride?: number,
  ): void => {
    const spanId = crypto.randomUUID()
    trace.push({
      schema: "wfxm.trace/0",
      traceId,
      runId,
      runtime: "wfxm",
      seq: seq++,
      ts: new Date(tsOverride ?? Date.now()).toISOString(),
      type,
      spanId,
      parentSpanId: rootSpanId,
      actor,
      payload,
    })
    if (type === "run.start") rootSpanId = spanId
  }

  const startedAt = Date.now()
  push("run.start", {
    taskId: task.id,
    scenarioId: hint.scenarioId,
    channel: "wechat",
    model: task.realModel ? "real" : "fixture",
  })

  const app = await makeAcceptanceApp({ noFixture: task.realModel === true })
  // 模型事件：生产 wiring 的 llm_call step 记录已带 token / costUsd /
  // request / response 元数据；这里按轮次切片导出成 eval TraceEvent。
  const tracer = getSharedLocalTracer()
  const modelTotals = {
    calls: 0,
    inputTokens: 0,
    outputTokens: 0,
    totalTokens: 0,
    costUsd: 0,
    costedCalls: 0,
  }
  const collectModelEvents = (cursor: number): void => {
    const events = tracer
      .list()
      .slice(cursor)
      .filter((event) => event.kind === "step" && event.name === "llm_call")
    for (const event of events) {
      const detail = event.detail ?? {}
      const request =
        detail["request"] !== null && typeof detail["request"] === "object"
          ? (detail["request"] as Record<string, unknown>)
          : undefined
      const response =
        detail["response"] !== null && typeof detail["response"] === "object"
          ? (detail["response"] as Record<string, unknown>)
          : undefined
      modelTotals.calls += 1
      if (event.token) {
        modelTotals.inputTokens += event.token.inputTokens
        modelTotals.outputTokens += event.token.outputTokens
        modelTotals.totalTokens += event.token.totalTokens
      }
      if (typeof event.costUsd === "number") {
        modelTotals.costUsd += event.costUsd
        modelTotals.costedCalls += 1
      }
      push(
        "model.request",
        {
          status: event.status,
          model: detail["model"] ?? null,
          ...(request ?? {}),
        },
        { kind: "agent", id: "wfxm" },
        event.createdAt - (event.durationMs ?? 0),
      )
      push(
        "model.response",
        {
          status: event.status,
          durationMs: event.durationMs ?? 0,
          ...(event.token
            ? {
                inputTokens: event.token.inputTokens,
                outputTokens: event.token.outputTokens,
                totalTokens: event.token.totalTokens,
              }
            : {}),
          ...(typeof event.costUsd === "number" ? { costUsd: event.costUsd } : {}),
          ...(response ?? {}),
          ...(event.status === "error" && typeof detail["reason"] === "string"
            ? { reason: detail["reason"] }
            : {}),
        },
        { kind: "system", id: "wfxm" },
        event.createdAt,
      )
    }
  }
  try {
    if (task.repoFixture) {
      cpSync(task.repoFixture, app.workspaceRoot, { recursive: true })
      push("test.run", { phase: "setup", repoFixture: task.repoFixture })
    }
    seedWorkspace(app.workspaceRoot, hint.fixtures?.seedFiles ?? [])

    // RAG 任务：把文档写进 documentStore；subject 与生产 memorySubject 同源
    // （owner 微信 id），否则 recall_document 查不到。
    const seedDocuments = hint.rag?.documents ?? []
    if (seedDocuments.length > 0) {
      const subject =
        (process.env["BUTLER_OWNER_WECHAT_ID"] ?? "")
          .split(/[,\s]+/)
          .map((part) => part.trim())
          .find((part) => part.length > 0) ?? "owner"
      const now = Date.now()
      for (const [index, doc] of seedDocuments.entries()) {
        const made = ingestDocumentRecord({
          subject,
          title: doc.title,
          format: doc.format ?? "markdown",
          text: doc.text,
          // 保持声明顺序，避免同一毫秒内 updatedAt 相同导致召回顺序不稳定。
          nowMs: now + index,
        })
        if (!made.ok) throw new Error(`文档 ${doc.title} 入库失败：${made.reason}`)
        await app.wiring.documentStore.create(made.value)
      }
      push("rag.seed", { count: seedDocuments.length, subject })
    }
    if (hint.rag?.expectation) {
      push("rag.expectation", { ...hint.rag.expectation })
    }

    const testsBefore = task.tests ? await runTests(app.workspaceRoot, task.tests) : undefined
    if (testsBefore) {
      push("test.run", {
        phase: "before",
        command: testsBefore.command,
        exitCode: testsBefore.exitCode,
        passed: testsBefore.passed,
      })
    }

    // 工具级轨迹：从 runtimeStore.audit_events 还原（capability.executed /
    // approval.requested）。参数由 capability-boundary 写入 detail.args（已脱敏）。
    const toolNames: string[] = []
    const toolResults: { name: string; ok: boolean }[] = []
    const toolCalls: { name: string; args?: Record<string, unknown> }[] = []
    const seenAudit = new Set<string>()

    const collectAudit = async (conversationId: string, windowMs: number): Promise<void> => {
      const audit = await app.wiring.runtimeStore.listRecentAuditEvents({
        conversationId,
        windowMs,
        limit: 500,
      })
      const rows = audit
        .filter(
          (e) => !seenAudit.has(e.auditId) && new Date(e.createdAt).getTime() >= startedAt - 1_000,
        )
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())

      for (const row of rows) {
        seenAudit.add(row.auditId)
        const detail = (row.detail ?? {}) as Record<string, unknown>
        const capability =
          typeof detail["capability"] === "string" ? detail["capability"] : undefined
        if (!capability) continue
        const executedAt = new Date(row.createdAt).getTime()

        if (row.action === "capability.executed") {
          const toolDuration = typeof detail["durationMs"] === "number" ? detail["durationMs"] : 0
          const ok = detail["ok"] === true
          const failReason = typeof detail["reason"] === "string" ? detail["reason"] : undefined
          const rawArgs = detail["args"]
          const callArgs =
            rawArgs && typeof rawArgs === "object" && !Array.isArray(rawArgs)
              ? (rawArgs as Record<string, unknown>)
              : undefined
          toolNames.push(capability)
          toolResults.push({ name: capability, ok })
          toolCalls.push({ name: capability, ...(callArgs ? { args: callArgs } : {}) })
          // RAG 证据：recall_* 在 capability.executed.detail.meta.retrieval 中
          // 回传 scope / query / hits（docId / rank / score）。导成独立事件，
          // Ragas 与失败样本定位都消费它，不必解析工具输出文本。
          const meta =
            detail["meta"] !== null && typeof detail["meta"] === "object"
              ? (detail["meta"] as Record<string, unknown>)
              : undefined
          const retrieval =
            meta?.["retrieval"] !== null && typeof meta?.["retrieval"] === "object"
              ? (meta["retrieval"] as Record<string, unknown>)
              : undefined
          if (retrieval) {
            push(
              "rag.retrieve",
              { capability, ...retrieval },
              { kind: "agent", id: "wfxm" },
              Math.max(startedAt, executedAt - toolDuration),
            )
          }
          push(
            "tool.call",
            { name: capability, source: "audit", ...(callArgs ? { args: callArgs } : {}) },
            { kind: "agent", id: "wfxm" },
            Math.max(startedAt, executedAt - toolDuration),
          )
          push(
            "tool.result",
            {
              name: capability,
              ok,
              durationMs: toolDuration,
              ...(failReason ? { reason: failReason } : {}),
            },
            { kind: "system", id: "wfxm" },
            executedAt,
          )
        } else if (row.action === "approval.requested") {
          toolNames.push(capability)
          push(
            "approval.request",
            {
              capability,
              stepId: detail["stepId"] ?? null,
              question: detail["question"] ?? null,
            },
            { kind: "agent", id: "wfxm" },
            executedAt,
          )
        }
      }
    }

    const replies: string[] = []
    const statuses: number[] = []
    let conversationId: string | undefined
    let firstDecision: string | undefined
    let totalToolCalls = 0

    const installFixtures = (): void => {
      if (task.realModel) return
      app.setFixtures({
        plan: hint.fixtures?.plan ?? [],
        exec: hint.fixtures?.exec ?? [],
        intake: hint.fixtures?.intake ?? [],
      })
    }
    // repo-task 的审批恢复需要沿用同一份 plan 游标，因此只在开始时装一次。
    if (task.repoFixture) installFixtures()

    for (const [index, content] of task.turns.entries()) {
      push("turn.start", { index: index + 1, input: content }, { kind: "owner", id: "u-owner" })
      const turnStartedAt = Date.now()
      const modelCursor = tracer.size()
      // chat-task 每轮重置 fixture 计数器，对齐 realistic.test.ts 的多轮语义。
      if (!task.repoFixture) installFixtures()
      const turnBudget =
        task.budget?.maxToolCalls !== undefined
          ? {
              ...task.budget,
              maxToolCalls: Math.max(0, task.budget.maxToolCalls - totalToolCalls),
            }
          : task.budget
      const reply = await sendWechatMessage(app, {
        content,
        ...(conversationId ? { conversationId } : {}),
        ...(task.messageIds?.[index] ? { messageId: task.messageIds[index] } : {}),
        // 把剩余工具预算传给 Run，让 loop 每轮看到剩余额度。
        ...(turnBudget ? { budget: turnBudget } : {}),
      })
      conversationId = reply.conversationId ?? conversationId
      replies.push(reply.reply ?? "")
      statuses.push(reply.status)
      totalToolCalls += reply.toolCalls ?? 0
      if (index === 0) firstDecision = reply.finalDecision

      if (conversationId) await collectAudit(conversationId, Date.now() - startedAt + 60_000)
      collectModelEvents(modelCursor)

      push("turn.end", {
        status: reply.status,
        finalDecision: reply.finalDecision ?? null,
        toolCalls: reply.toolCalls ?? 0,
        replyLen: (reply.reply ?? "").length,
        latencyMs: Date.now() - turnStartedAt,
      })
    }

    const durationMs = Date.now() - startedAt
    // 变更规模在测试前采样，避免测试命令自己产生的临时文件污染 diff。
    const repoDiff = task.repoFixture ? diffWorkspace(task.repoFixture, app.workspaceRoot) : null
    if (repoDiff) push("workspace.diff", { ...repoDiff })
    const testsAfter = task.tests ? await runTests(app.workspaceRoot, task.tests) : undefined
    if (testsAfter) {
      push("test.run", {
        phase: "after",
        command: testsAfter.command,
        exitCode: testsAfter.exitCode,
        passed: testsAfter.passed,
      })
    }
    // 工作区终态：只回读任务声明的路径，避免把整个沙箱内容带进结果。
    const workspace: Record<string, string | null> = {}
    for (const path of task.workspacePaths ?? []) {
      try {
        workspace[path] = readFileSync(resolveInsideWorkspace(app.workspaceRoot, path), "utf8")
      } catch {
        workspace[path] = null
      }
    }
    push("run.end", { status: "ok", durationMs })

    emitResult({
      status: statuses[0] ?? 0,
      statuses,
      reply: replies[0] ?? "",
      replies,
      finalDecision: firstDecision,
      steps: totalToolCalls,
      turns: statuses.length,
      toolNames,
      toolResults,
      toolCalls,
      ...(modelTotals.calls > 0
        ? {
            model: {
              calls: modelTotals.calls,
              inputTokens: modelTotals.inputTokens,
              outputTokens: modelTotals.outputTokens,
              totalTokens: modelTotals.totalTokens,
            },
          }
        : {}),
      // 只有至少一次调用拿到计价时才上报；否则保持“未知”，不写 0。
      ...(modelTotals.costedCalls > 0 ? { costUsd: modelTotals.costUsd } : {}),
      ...(task.tests && testsBefore && testsAfter
        ? {
            tests: {
              command: task.tests.command,
              before: testsBefore,
              after: testsAfter,
            },
          }
        : {}),
      ...(Object.keys(workspace).length > 0 ? { workspace } : {}),
      ...(repoDiff ? { diff: repoDiff } : {}),
      durationMs,
      trace,
    })
  } finally {
    await app.close()
  }
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err)
  emitResult({ error: message })
  process.exit(1)
})
