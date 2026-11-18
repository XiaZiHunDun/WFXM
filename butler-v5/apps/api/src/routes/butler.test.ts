import { describe, expect, it } from "vitest"
import { Hono } from "hono"
import type { ButlerTaskPort, ButlerTaskRef } from "@butler/ports/core/butler-task.js"
import { ButlerRuntime, MemoryButlerSessionStore } from "@butler/runtime/butler/index.js"
import type { ButlerAssembly } from "../butler-assembly.js"
import type { Wiring } from "../wiring.js"
import { parseProjectRoots, registerButlerRoutes } from "./butler.js"

const env: NodeJS.ProcessEnv = {
  BUTLER_V5_INBOUND_SHARED_SECRET: "test-secret",
}

function fakeTasks(initial: readonly ButlerTaskRef[] = []) {
  const tasks = [...initial]
  const approvals: { taskId: string; approved: boolean }[] = []
  const port: ButlerTaskPort & { readonly approvals: typeof approvals } = {
    approvals,
    async start(input) {
      return { taskId: "t-new", projectId: input.projectId, status: "idle" }
    },
    async status(taskId) {
      return tasks.find((task) => task.taskId === taskId) ?? null
    },
    async list(projectId) {
      return projectId ? tasks.filter((task) => task.projectId === projectId) : tasks
    },
    async approve(taskId, approved) {
      approvals.push({ taskId, approved })
      const task = tasks.find((entry) => entry.taskId === taskId)
      return task ? { ...task, status: "idle", pending: undefined } : null
    },
  }
  return port
}

function fakeAssembly(tasks?: ButlerTaskPort): ButlerAssembly {
  const butler = new ButlerRuntime({
    model: {
      async complete() {
        return { content: "好的" }
      },
    },
    store: new MemoryButlerSessionStore(),
    ...(tasks === undefined ? {} : { tasks }),
    clock: () => "2026-11-17T10:00:00.000Z",
  })
  return { butler, tasks: null as never, runner: null as never }
}

function makeApp(createAssembly: () => ButlerAssembly): Hono {
  const app = new Hono()
  registerButlerRoutes(app, {} as Wiring, { env, createAssembly })
  return app
}

async function post(
  app: Hono,
  body: unknown,
  secret: string | null = "test-secret",
): Promise<Response> {
  return app.request("/v1/wechat/butler/inbound", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(secret === null ? {} : { "x-inbound-secret": secret }),
    },
    body: JSON.stringify(body),
  })
}

describe("registerButlerRoutes", () => {
  it("serves a plain message through the butler runtime", async () => {
    const app = makeApp(() => fakeAssembly())
    const res = await post(app, {
      apiVersion: "v1",
      fromUserId: "u1",
      conversationId: "c1",
      projectId: "p1",
      content: "你好",
    })

    expect(res.status).toBe(200)
    expect(await res.json()).toMatchObject({
      conversationId: "c1",
      reply: "好的",
      route: "agent",
      sent: true,
    })
  })

  it("routes an approval payload to the task layer", async () => {
    const tasks = fakeTasks([
      {
        taskId: "t1",
        projectId: "p1",
        status: "paused",
        pending: { toolName: "write", reason: "需要审批" },
      },
    ])
    const app = makeApp(() => fakeAssembly(tasks))
    const res = await post(app, {
      apiVersion: "v1",
      fromUserId: "u1",
      conversationId: "c1",
      projectId: "p1",
      approvalPayload: "approve:t1",
    })

    expect(res.status).toBe(200)
    expect(await res.json()).toMatchObject({ route: "rule", rule: "approval-card", taskId: "t1" })
    expect(tasks.approvals).toEqual([{ taskId: "t1", approved: true }])
  })

  it("rejects an unparsable approval payload", async () => {
    const app = makeApp(() => fakeAssembly())
    const res = await post(app, {
      apiVersion: "v1",
      fromUserId: "u1",
      conversationId: "c1",
      projectId: "p1",
      approvalPayload: "button-42",
    })

    expect(res.status).toBe(400)
  })

  it("requires the inbound shared secret", async () => {
    const app = makeApp(() => fakeAssembly())
    const res = await post(app, { apiVersion: "v1", fromUserId: "u1", content: "hi" }, null)
    expect(res.status).toBe(401)
  })

  it("validates the body before building the runtime", async () => {
    const app = makeApp(() => {
      throw new Error("should not be called")
    })
    const res = await post(app, { apiVersion: "v1" })
    expect(res.status).toBe(400)
  })

  it("returns 503 when the runtime cannot be assembled", async () => {
    const app = makeApp(() => {
      throw new Error("MINIMAX_BASE_URL is required for the pi task layer")
    })
    const res = await post(app, {
      apiVersion: "v1",
      fromUserId: "u1",
      conversationId: "c1",
      projectId: "p1",
      content: "你好",
    })

    expect(res.status).toBe(503)
    expect(await res.json()).toMatchObject({
      error: expect.stringContaining("MINIMAX_BASE_URL"),
    })
  })
})

describe("parseProjectRoots", () => {
  it("parses a JSON map", () => {
    expect(parseProjectRoots({ BUTLER_V5_PROJECT_ROOTS: '{"p1":"/srv/p1"}' })).toEqual({
      p1: "/srv/p1",
    })
  })

  it("returns an empty map when unset", () => {
    expect(parseProjectRoots({})).toEqual({})
  })

  it("rejects malformed or non-object values", () => {
    expect(() => parseProjectRoots({ BUTLER_V5_PROJECT_ROOTS: "nope" })).toThrow(/valid JSON/)
    expect(() => parseProjectRoots({ BUTLER_V5_PROJECT_ROOTS: '["/srv/p1"]' })).toThrow(
      /object of projectId/,
    )
    expect(() => parseProjectRoots({ BUTLER_V5_PROJECT_ROOTS: '{"p1":12}' })).toThrow(
      /invalid root for p1/,
    )
  })
})
