import { describe, expect, it } from "vitest"
import type { ChannelPort, ChannelKind, ChannelRecipient } from "./channel.js"

describe("Channel Port contract", () => {
  it("accepts an in-memory ChannelPort that implements sendText", async () => {
    const captured: { recipient: ChannelRecipient; content: string }[] = []
    const port: ChannelPort = {
      channelKind: "wechat",
      async sendText(input) {
        captured.push({ recipient: input.recipient, content: input.content })
        return { ok: true, messageId: "m-1" }
      },
    }
    const result = await port.sendText({
      recipient: { address: "user-1", channelKind: "wechat" },
      content: "hello",
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.messageId).toBe("m-1")
    expect(captured).toHaveLength(1)
    expect(captured[0]?.content).toBe("hello")
    expect(captured[0]?.recipient.channelKind).toBe("wechat")
  })

  it("exposes channelKind discriminator for runtime lookup", () => {
    const slackLike: ChannelPort = {
      channelKind: "slack",
      async sendText() {
        return { ok: true, messageId: null }
      },
    }
    expect(slackLike.channelKind).toBe("slack")
    const kinds: readonly ChannelKind[] = ["wechat", "slack", "telegram"]
    expect(kinds).toContain(slackLike.channelKind)
  })
})
