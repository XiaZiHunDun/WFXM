/**
 * Channel Port (DESIGN §7) — outbound communication surface. Sending replies
 * and media to the recipient's channel is the responsibility of this Port.
 *
 * Inbound triggering is the Trigger Adapter concern (DESIGN §8) and stays
 * separate — the Channel Port does NOT receive inbound traffic. Each
 * channel type (WeChat, Slack, Telegram, ...) provides its own concrete
 * implementation behind this interface; the Composition Root registers the
 * active set in the wiring registry and runtime consumers resolve by
 * `channelKind`.
 *
 * Per DESIGN §7 "ports-stable × real-need driven": adding a second live
 * channel (Slack, per DESIGN §18 trigger) is what motivated this Port.
 */
export type ChannelKind = "wechat" | "slack" | "telegram"

export interface ChannelRecipient {
  /** Channel-specific address (WeChat: user ID; Slack: DM channel ID; ...). */
  readonly address: string
  readonly channelKind: ChannelKind
}

export type ChannelSendResult =
  | { readonly ok: true; readonly messageId: string | null }
  | { readonly ok: false; readonly reason: string }

export interface ChannelPort {
  readonly channelKind: ChannelKind
  /** Send plain text content to the recipient. */
  readonly sendText: (input: {
    readonly recipient: ChannelRecipient
    readonly content: string
  }) => Promise<ChannelSendResult>
}
