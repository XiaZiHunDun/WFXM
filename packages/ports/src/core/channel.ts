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
export type ChannelKind = "wechat" | "slack" | "telegram" | "generic"

export interface ChannelRecipient {
  /** Channel-specific address (WeChat: user ID; Slack: DM channel ID; ...). */
  readonly address: string
  readonly channelKind: ChannelKind
}

export type ChannelSendResult =
  | { readonly ok: true; readonly messageId: string | null }
  | { readonly ok: false; readonly reason: string }

/** Uniform reason implementations return for blank text. */
export const EMPTY_CHANNEL_TEXT_REASON = "empty text"

/** True when there is nothing an owner could read. */
export function isBlankChannelText(content: string): boolean {
  return content.trim().length === 0
}

/**
 * Outbound contract shared by every channel:
 *
 * - `content` is one logical message. Implementations may split it to fit
 *   their own transport limit, but must not silently drop the tail.
 * - Blank text returns `{ok:false, reason: EMPTY_CHANNEL_TEXT_REASON}`
 *   without calling the transport.
 * - `sendText` never throws; transport/network failures come back as
 *   `{ok:false, reason}`. Implementations bound their own calls with a
 *   timeout.
 * - A successful send reports `ok:true`; `messageId` may be `null` when the
 *   upstream API has no stable identifier.
 */
export interface ChannelPort {
  readonly channelKind: ChannelKind
  /** Send plain text content to the recipient. */
  readonly sendText: (input: {
    readonly recipient: ChannelRecipient
    readonly content: string
  }) => Promise<ChannelSendResult>
}
