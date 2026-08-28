/**
 * Slack channel adapter — protocol + outbound surface.
 *
 * Mirrors the WeChat adapter layout (`packages/adapters/src/wechat/`):
 *   - slack-media.ts:          inbound media classification + shared types
 *   - slack-protocol.ts:       signing-secret verify + event payload parse
 *   - slack-outbound.ts:       chat.postMessage
 *   - slack-outbound-media.ts: files.upload
 *
 * Apps/api orchestration (intake routing, deliverChannelReply glue) lives
 * in `apps/api/src/{channel-inbound,channel-outbound}.ts` — not here.
 */
export * from "./slack-media.js"
export type { ChannelInboundMedia, ChannelMediaContent, ChannelMediaKind } from "./slack-media.js"
export * from "./slack-protocol.js"
export type { SlackWebhookParseResult } from "./slack-protocol.js"
export * from "./slack-outbound.js"
export type { SlackOutboundConfig, SlackOutboundResult } from "./slack-outbound.js"
export * from "./slack-outbound-media.js"