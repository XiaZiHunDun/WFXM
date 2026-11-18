import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { createWfxmMemoryPorts } from "@agent-rag/adapters"
import { AgentRagClient } from "@agent-rag/client"
import { createMemoryRecord } from "@agent-rag/core"
import { JsonTextStore } from "@agent-rag/store-text"
import {
  ButlerRuntime,
  MemoryButlerSessionStore,
  type ButlerModelPort,
} from "@butler/runtime/butler/index.js"

let root: string
let file: string

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "butler-consistency-"))
  file = join(root, "memory.json")
})

afterEach(() => {
  rmSync(root, { recursive: true, force: true })
})

function userMemory(input: {
  readonly text: string
  readonly title?: string
  readonly supersedes?: readonly string[]
  readonly validFrom?: string
  readonly validTo?: string
}) {
  return createMemoryRecord({
    scope: "user",
    ownerId: "user-1",
    kind: "preference",
    title: input.title ?? "沟通偏好",
    text: input.text,
    source: { kind: "manual", ref: input.text },
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
    ...(input.supersedes === undefined ? {} : { supersedes: input.supersedes }),
    ...(input.validFrom === undefined ? {} : { validFrom: input.validFrom }),
    ...(input.validTo === undefined ? {} : { validTo: input.validTo }),
  })
}

describe("butler memory consistency (P2)", () => {
  it("injects only the current valid facts", async () => {
    const client = new AgentRagClient({ store: await JsonTextStore.open(file) })
    const oldPreference = userMemory({ text: "沟通语言使用英文" })
    await client.remember(oldPreference)

    const replacement = userMemory({
      text: "沟通语言使用中文",
      supersedes: [oldPreference.id],
      validFrom: "2026-06-01T00:00:00.000Z",
    })
    const retired = await client.remember(replacement)
    expect(retired).toEqual([oldPreference.id])
    expect((await client.get(oldPreference.id))?.validTo).toBe("2026-06-01T00:00:00.000Z")

    await client.remember(
      userMemory({
        title: "称谓",
        text: "称呼我为老板",
        validFrom: "2026-01-01T00:00:00.000Z",
        validTo: "2026-03-01T00:00:00.000Z",
      }),
    )

    const memory = createWfxmMemoryPorts({ client, ownerId: "user-1" })
    const prompts: string[] = []
    let reply = 0
    const model: ButlerModelPort = {
      async complete(request) {
        const system = request.messages.find((message) => message.role === "system")
        prompts.push(system?.content ?? "")
        reply += 1
        return { content: `收到${reply}` }
      },
    }
    const butler = new ButlerRuntime({
      model,
      store: new MemoryButlerSessionStore(),
      memory: memory.butler,
      clock: () => "2026-11-17T10:00:00.000Z",
    })

    await butler.handle({
      conversationId: "c1",
      userId: "user-1",
      content: "沟通语言用什么？",
    })
    await butler.handle({
      conversationId: "c1",
      userId: "user-1",
      content: "你该怎么称呼我？",
    })

    expect(prompts[0]).toContain("沟通语言使用中文")
    expect(prompts[0]).not.toContain("沟通语言使用英文")
    // Expired facts never reach the prompt, even when the query matches them.
    expect(prompts[1]).not.toContain("称呼我为老板")
  })
})
