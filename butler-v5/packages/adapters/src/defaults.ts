/**
 * Shared default timeout constants (D73 T3 audit #19 CQ-014).
 *
 * Single source of truth for the recurring 30_000 ms fallback across
 * MCP transports, media uploads, and LLM calls. Previously hardcoded
 * as magic numbers in 7+ sites:
 *   - packages/adapters/src/mcp/{http,sse,stdio}-transport.ts
 *   - packages/adapters/src/slack/slack-outbound-media.ts
 *   - packages/adapters/src/wechat/ilink-media.ts
 *   - apps/api/src/channel-outbound-media.ts
 *   - apps/api/src/subagent-worker.ts (LLM_TIMEOUT_MS)
 *
 * Each timeout is a different surface (LLM / MCP / media) but the
 * default 30_000 ms is intentional parity — operator can override via
 * the per-site env knob (e.g. BUTLER_V5_MCP_TIMEOUT_MS for MCP sites,
 * which env-util.ts:parseMcpTimeoutMs already handles).
 *
 * Site-specific knobs (60_000 in wechat-quality-gate.ts) intentionally
 * retain their own defaults — don't extend these constants to those sites.
 */

export const DEFAULT_MCP_TIMEOUT_MS = 30_000
export const DEFAULT_MEDIA_TIMEOUT_MS = 30_000
export const DEFAULT_LLM_TIMEOUT_MS = 30_000