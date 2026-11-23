import { afterEach, beforeEach, describe, expect, it } from "vitest"
import type { ButlerModelPort } from "@butler/runtime/butler/index.js"
import { ButlerRuntime } from "@butler/runtime/butler/index.js"
import type { ChannelPort } from "@butler/ports/core/channel.js"
import type { ButlerAssembly } from "./butler-assembly.js"
import { ChannelInboundError, handleChannelInbound } from "./channel-inbound.js"
import type { ButlerOwnerRef, ButlerRuntimeProvider } from "./butler-runtime-provider.js"
import type { Wiring } from "./wiring.js"

const ALLOWLIST_KEY = "BUTLER_V5_CHANNEL_ALLOWLIST"
const PROJECTS_KEY = "BUTLER_V5_CHANNEL_PROJECTS"
const previousAllowlist = process.env[ALLOWLIST_KEY]
const previousProjects = process.env[PROJECTS_KEY]

beforeEach(() => {
  process.env[ALLOWLIST_KEY] = "slack"
  process.env[PROJECTS_KEY] = '{"slack":"p1"}'
})

afterEach(() => {
  if (previousAllowlist === undefined) delete process.env[ALLOWLIST_KEY]
  else process.env[ALLOWLIST_KEY] = previousAllowlist
  if (previousProjects === undefined) delete process.env[PROJECTS_KEY]
  else process.env[PROJECTS_KEY] = previousProjects
})

function fakeWiring(): Wiring {
  return {
    eventBridge: {
      async appendConversationEvent() {
        return undefined
      },
    },
  } as unknown as Wiring
}

function fakeModel(): ButlerModelPort {
  return {
    async complete() {
      return { content: "不应调用模型" }
    },
  }
}

function fakeProvider(
  butler: ButlerRuntime,
  options: { readonly fail?: Error } = {},
): ButlerRuntimeProvider & {
  readonly owners: Map<string, ButlerOwnerRef>
  assemblyCalls: number
} {
  const owners = new Map<string, ButlerOwnerRef>()
  const provider = {
    owners,
    assemblyCalls: 0,
    async assembly(): Promise<ButlerAssembly> {
      provider.assemblyCalls += 1
      if (options.fail) throw options.fail
      return { butler } as unknown as ButlerAssembly
    },
    rememberOwner(conversationId: string, owner: ButlerOwnerRef) {
      owners.set(conversationId, owner)
    },
  }
  return provider
}

function fakeChannel(): ChannelPort & { readonly sent: string[] } {
  const sent: string[] = []
  return {
    channelKind: "slack",
    sent,
    async sendText(input) {
      sent.push(input.content)
      return { ok: true, messageId: null }
    },
  }
}

describe("channel cutover", () => {
  it("routes a slack turn through the butler runtime when enabled", async () => {
    const provider = fakeProvider(new ButlerRuntime({ model: fakeModel() }))
    const channel = fakeChannel()

    const result = await handleChannelInbound({
      wiring: fakeWiring(),
      channelId: "slack",
      fromSubject: "U1",
      content: "/help",
      messageId: "m-1",
      conversationId: "c1",
      engine: "butler",
      butler: provider,
      channel,
      ownerThreadTs: "thread-1",
    })

    expect(result.meta.finalDecision).toBe("Respond")
    expect(result.reply).toContain("/retry [任务ID]")
    expect(result.delivered).toBe(true)
    expect(channel.sent[0]).toContain("/status")
    expect(provider.owners.get("c1")).toMatchObject({
      channelKind: "slack",
      address: "U1",
      threadTs: "thread-1",
    })
    expect(provider.assemblyCalls).toBe(1)
  })

  it("reports a missing provider as 503", async () => {
    await expect(
      handleChannelInbound({
        wiring: fakeWiring(),
        channelId: "slack",
        fromSubject: "U1",
        content: "/help",
        conversationId: "c1",
        engine: "butler",
      }),
    ).rejects.toMatchObject({ status: 503 })
  })

  it("reports an assembly failure as a readable 503", async () => {
    const provider = fakeProvider(new ButlerRuntime({ model: fakeModel() }), {
      fail: new Error("MINIMAX_API_KEY missing"),
    })

    await expect(
      handleChannelInbound({
        wiring: fakeWiring(),
        channelId: "slack",
        fromSubject: "U1",
        content: "/help",
        conversationId: "c1",
        engine: "butler",
        butler: provider,
      }),
    ).rejects.toBeInstanceOf(ChannelInboundError)
  })

  it("never assembles the butler runtime in legacy mode", async () => {
    const provider = fakeProvider(new ButlerRuntime({ model: fakeModel() }))
    try {
      await handleChannelInbound({
        wiring: fakeWiring(),
        channelId: "slack",
        fromSubject: "U1",
        content: "你好",
        conversationId: "c1",
        engine: "legacy",
        butler: provider,
      })
    } catch {
      // The legacy pipeline needs the full RunEngine wiring; only the
      // routing guard is under test here.
    }
    expect(provider.assemblyCalls).toBe(0)
  })
})
