/**
 * WeChat ChannelPort — iLink-backed implementation of DESIGN §7 Channel Port.
 *
 * Composition Root instantiates this via `createWechatChannelPort(client)`
 * when `BUTLER_V5_ILINK_ENABLED=1` (and `WECHAT_TOKEN` set). Runtime callers
 * resolve `wiring.channels.get("wechat")?.sendText(...)` to deliver replies
 * and proactive notifications without holding a direct iLink reference.
 */
import { ilinkSendMessage, type ILinkClientConfig } from "./ilink.js"
import type {
  ChannelKind,
  ChannelPort,
  ChannelRecipient,
  ChannelSendResult,
} from "@butler/ports/core/channel.js"

export function createWechatChannelPort(client: ILinkClientConfig): ChannelPort {
  return {
    channelKind: "wechat" satisfies ChannelKind,
    async sendText(input: {
      readonly recipient: ChannelRecipient
      readonly content: string
    }): Promise<ChannelSendResult> {
      const result = await ilinkSendMessage(client, {
        to: input.recipient.address,
        text: input.content,
      })
      if (!result.ok) {
        return { ok: false, reason: result.reason ?? "ilink send failed" }
      }
      // iLink sendmessage response shape is opaque; we don't promote a message ID
      // until the upstream API exposes a stable typed identifier.
      return { ok: true, messageId: null }
    },
  }
}
