import { describe, expect, it } from "vitest"
import type { ButlerMemoryPort, RecalledUserMemory } from "@butler/ports/core/butler-memory.js"
import {
  ButlerRuntime,
  MemoryButlerSessionStore,
  type ButlerModelPort,
  type ButlerModelReply,
} from "./index.js"

const FIXED = "2026-11-17T10:00:00.000Z"
const clock = () => FIXED

interface CapturedRequest {
  readonly messages: readonly { role: string; content: string }[]
}

function scriptedModel(replies: readonly ButlerModelReply[] = []) {
  const requests: CapturedRequest[] = []
  let index = 0
  const model: ButlerModelPort = {
    async complete(request) {
      requests.push({
        messages: request.messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
      })
      const reply = replies[Math.min(index, replies.length - 1)] ?? { content: "收到" }
      index += 1
      return reply
    },
  }
  return { model, requests }
}

interface MemoryEntry {
  readonly title: string
  readonly text: string
  readonly keywords?: readonly string[]
}

function keywordMemory(entries: readonly MemoryEntry[]) {
  const calls: string[] = []
  const port: ButlerMemoryPort = {
    async recordSessionSummary() {
      // not under test
    },
    async recallUserMemory(query) {
      calls.push(query)
      const matched =
        query.trim().length === 0
          ? entries
          : entries.filter(
              (entry) =>
                entry.keywords === undefined ||
                entry.keywords.some((keyword) => query.includes(keyword)),
            )
      return matched.map((entry): RecalledUserMemory => ({ title: entry.title, text: entry.text }))
    },
  }
  return { port, calls }
}

function userTurns(store: MemoryButlerSessionStore, conversationId: string): Promise<number> {
  return store
    .load(conversationId)
    .then((session) =>
      session ? session.messages.filter((message) => message.role === "user").length : 0,
    )
}

/** Ambiguous follow-ups only make sense with prior history. */
async function seedHistory(store: MemoryButlerSessionStore): Promise<void> {
  await store.save({
    conversationId: "c1",
    userId: "u1",
    messages: [
      { role: "user", content: "登录接口的限流怎么做的？" },
      { role: "assistant", content: "用令牌桶。" },
    ],
    createdAt: FIXED,
    updatedAt: FIXED,
  })
}

describe("butler context window (P0)", () => {
  it("keeps only the window turns and folds older turns into the summary", async () => {
    const store = new MemoryButlerSessionStore()
    const { model, requests } = scriptedModel()
    const butler = new ButlerRuntime({ model, store, clock, windowTurns: 4 })

    for (let turn = 1; turn <= 16; turn += 1) {
      await butler.handle({
        conversationId: "c1",
        userId: "u1",
        content: `第${turn}轮：请记住约束${turn}`,
      })
    }

    expect(await userTurns(store, "c1")).toBe(4)
    const session = await store.load("c1")
    expect(session?.summary).toContain("第1轮")
    expect(session?.summary).toContain("用户：第1轮")

    const firstPrompt = requests[0]?.messages.find((message) => message.role === "system")
    expect(firstPrompt?.content).not.toContain("[此前对话摘要]")

    const lastPrompt = requests.at(-1)?.messages ?? []
    const system = lastPrompt.find((message) => message.role === "system")
    expect(system?.content).toContain("[此前对话摘要]")
    expect(system?.content).toContain("第1轮")
    const lastUserMessages = lastPrompt.filter((message) => message.role === "user")
    expect(lastUserMessages).toHaveLength(4)
    expect(lastUserMessages.at(0)?.content).toContain("第13轮")
    expect(lastUserMessages.at(-1)?.content).toContain("第16轮")
  })

  it("folds the oldest turns when the prompt budget is exceeded", async () => {
    const store = new MemoryButlerSessionStore()
    const { model, requests } = scriptedModel()
    const butler = new ButlerRuntime({
      model,
      store,
      clock,
      windowTurns: 12,
      maxPromptChars: 2_000,
    })

    const filler = "x".repeat(600)
    for (let turn = 1; turn <= 6; turn += 1) {
      await butler.handle({
        conversationId: "c1",
        userId: "u1",
        content: `第${turn}轮 ${filler}`,
      })
    }

    const lastPrompt = requests.at(-1)?.messages ?? []
    const system = lastPrompt.find((message) => message.role === "system")
    expect(system?.content).toContain("[此前对话摘要]")

    const historyChars = lastPrompt
      .filter((message) => message.role !== "system")
      .reduce((total, message) => total + message.content.length, 0)
    expect(historyChars).toBeLessThan(6 * (600 + 10))
    // The budget folds older turns out of the stored transcript as well.
    expect(await userTurns(store, "c1")).toBeLessThan(6)
    expect((await store.load("c1"))?.summary).toContain("第1轮")
  })
})

describe("butler recall strategy (P1)", () => {
  it("rewrites an ambiguous query after a miss and recalls again", async () => {
    const memory = keywordMemory([
      { title: "限流方案", text: "登录接口用令牌桶限流", keywords: ["限流"] },
    ])
    const { model, requests } = scriptedModel([
      { content: "登录限流如何扩展" },
      { content: "在限流器里加白名单。" },
    ])
    const store = new MemoryButlerSessionStore()
    await seedHistory(store)
    const butler = new ButlerRuntime({
      model,
      store,
      memory: memory.port,
      clock,
    })

    const result = await butler.handle({
      conversationId: "c1",
      userId: "u1",
      content: "这个怎么扩展？",
    })

    expect(result.route).toBe("agent")
    expect(result.reply).toBe("在限流器里加白名单。")
    expect(result.traces).toContain("memory:rewrite")
    expect(memory.calls).toEqual(["这个怎么扩展？", "登录限流如何扩展"])
    expect(requests).toHaveLength(2)
    const agentSystem = requests[1]?.messages.find((message) => message.role === "system")
    expect(agentSystem?.content).toContain("限流方案")
  })

  it("falls back to recent memory when the rewrite still misses", async () => {
    const memory = keywordMemory([
      { title: "过往决策", text: "发布前必须先跑测试", keywords: ["永远不匹配"] },
    ])
    const { model } = scriptedModel([{ content: "另一个无关查询" }, { content: "好的" }])
    const store = new MemoryButlerSessionStore()
    await seedHistory(store)
    const butler = new ButlerRuntime({
      model,
      store,
      memory: memory.port,
      clock,
    })

    const result = await butler.handle({
      conversationId: "c1",
      userId: "u1",
      content: "那个呢？",
    })

    expect(result.traces).toContain("memory:recall:fallback")
    expect(memory.calls).toEqual(["那个呢？", "另一个无关查询", ""])
  })

  it("serves repeated recall queries from the cache", async () => {
    const memory = keywordMemory([{ title: "画像", text: "偏好中文" }])
    const { model } = scriptedModel()
    const butler = new ButlerRuntime({
      model,
      store: new MemoryButlerSessionStore(),
      memory: memory.port,
      clock,
    })

    await butler.handle({ conversationId: "c1", userId: "u1", content: "记住我偏好中文" })
    const second = await butler.handle({
      conversationId: "c1",
      userId: "u1",
      content: "记住我偏好中文",
    })

    expect(memory.calls).toHaveLength(1)
    expect(second.traces).toContain("memory:recall:cache")
  })

  it("skips rewriting when the query is self-contained", async () => {
    const memory = keywordMemory([{ title: "不会命中", text: "x", keywords: ["无关"] }])
    const { model, requests } = scriptedModel([{ content: "请检查网关配置。" }])
    const butler = new ButlerRuntime({
      model,
      store: new MemoryButlerSessionStore(),
      memory: memory.port,
      clock,
    })

    const result = await butler.handle({
      conversationId: "c1",
      userId: "u1",
      content: "如何配置网关超时时间",
    })

    expect(result.traces).not.toContain("memory:rewrite")
    expect(requests).toHaveLength(1)
    expect(memory.calls).toEqual(["如何配置网关超时时间"])
  })
})
