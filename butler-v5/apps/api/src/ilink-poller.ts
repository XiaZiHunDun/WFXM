/**
 * v5 native iLink poller — long-poll Tencent iLink, POST /v1/wechat/inbound,
 * send the butler reply back via sendmessage.
 *
 * Opt-in: BUTLER_V5_ILINK_ENABLED=1 plus WECHAT_TOKEN.
 * Started from the CLI after Hono is listening so inbound is reachable.
 */
import {
  ilinkGetUpdates,
  ilinkSendMessage,
  inboundFromIlinkMsg,
  isIlinkGroupMessage,
  isIlinkOk,
  isSessionExpired,
  type ILinkClientConfig,
  type ILinkResult,
} from "@butler/adapters"
import {
  isDmAllowed,
  parseIlinkPollerConfig,
  type DmPolicy,
  type IlinkPollerConfig,
} from "./ilink-config.js"
import { loadSyncBuf, saveSyncBuf } from "./ilink-sync.js"

export type IlinkPollerLogger = {
  readonly warn: (msg: string, ...args: unknown[]) => void
  readonly error: (msg: string, ...args: unknown[]) => void
}

export type IlinkPollerHandle = {
  readonly stop: () => void
}

export type IlinkPollState = {
  syncBuf: string
  readonly seenIds: Set<string>
}

export type IlinkCycleDeps = {
  readonly getUpdates: (syncBuf: string) => Promise<ILinkResult<Record<string, unknown>>>
  readonly postInbound: (input: {
    readonly fromUserId: string
    readonly content: string
    readonly messageId: string
  }) => Promise<ILinkResult<string>>
  readonly sendMessage: (input: {
    readonly to: string
    readonly text: string
    readonly contextToken?: string
  }) => Promise<ILinkResult<unknown>>
  readonly accountId: string
  readonly emptyPollDelayMs: number
  readonly sessionExpiredSleepMs: number
  readonly sleep: (ms: number) => Promise<void>
  readonly dmPolicy?: DmPolicy
  readonly allowedUserIds?: readonly string[]
  readonly dropGroups?: boolean
  readonly persistSyncBuf?: (syncBuf: string) => void
}

export type IlinkCycleStats = {
  readonly processed: number
  readonly sent: number
  readonly skipped: number
  readonly expired: boolean
  readonly empty: boolean
}

const defaultLogger: IlinkPollerLogger = {
  warn: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.warn(msg, ...args)
  },
  error: (msg, ...args) => {
    // eslint-disable-next-line no-console -- operator log when no logger injected
    console.error(msg, ...args)
  },
}

function msgsFromResponse(response: Record<string, unknown>): unknown[] {
  const msgs = response["msgs"]
  return Array.isArray(msgs) ? msgs : []
}

export async function runIlinkPollCycle(
  deps: IlinkCycleDeps,
  state: IlinkPollState,
): Promise<IlinkCycleStats> {
  const polled = await deps.getUpdates(state.syncBuf)
  if (!polled.ok) {
    await deps.sleep(deps.emptyPollDelayMs)
    return { processed: 0, sent: 0, skipped: 0, expired: false, empty: true }
  }
  const response = polled.value
  const nextBuf = response["get_updates_buf"]
  if (typeof nextBuf === "string" && nextBuf.length > 0) {
    state.syncBuf = nextBuf
    deps.persistSyncBuf?.(nextBuf)
  }
  if (isSessionExpired(response)) {
    await deps.sleep(deps.sessionExpiredSleepMs)
    return { processed: 0, sent: 0, skipped: 0, expired: true, empty: true }
  }
  if (!isIlinkOk(response)) {
    await deps.sleep(deps.emptyPollDelayMs)
    return { processed: 0, sent: 0, skipped: 0, expired: false, empty: true }
  }

  const msgs = msgsFromResponse(response)
  if (msgs.length === 0) {
    await deps.sleep(deps.emptyPollDelayMs)
    return { processed: 0, sent: 0, skipped: 0, expired: false, empty: true }
  }

  const dmPolicy = deps.dmPolicy ?? "open"
  const allowedUserIds = deps.allowedUserIds ?? []
  const dropGroups = deps.dropGroups ?? true

  let processed = 0
  let sent = 0
  let skipped = 0
  for (const msg of msgs) {
    if (dropGroups && isIlinkGroupMessage(msg)) {
      skipped += 1
      continue
    }
    const inbound = inboundFromIlinkMsg(msg)
    if (!inbound) {
      skipped += 1
      continue
    }
    if (deps.accountId && inbound.fromUserId === deps.accountId) {
      skipped += 1
      continue
    }
    if (!isDmAllowed(inbound.fromUserId, dmPolicy, allowedUserIds)) {
      skipped += 1
      continue
    }
    const dedupKey = inbound.messageId || `${inbound.fromUserId}:${inbound.content}`
    if (state.seenIds.has(dedupKey)) {
      skipped += 1
      continue
    }
    state.seenIds.add(dedupKey)
    if (state.seenIds.size > 2000) {
      const first = state.seenIds.values().next().value
      if (typeof first === "string") {
        state.seenIds.delete(first)
      }
    }
    processed += 1
    const reply = await deps.postInbound({
      fromUserId: inbound.fromUserId,
      content: inbound.content,
      messageId: inbound.messageId,
    })
    if (!reply.ok) {
      continue
    }
    const sentResult = await deps.sendMessage({
      to: inbound.fromUserId,
      text: reply.value,
      ...(inbound.contextToken ? { contextToken: inbound.contextToken } : {}),
    })
    if (sentResult.ok) {
      sent += 1
    }
  }
  return { processed, sent, skipped, expired: false, empty: false }
}

async function postInboundHttp(
  inboundUrl: string,
  timeoutMs: number,
  input: { readonly fromUserId: string; readonly content: string; readonly messageId: string },
  fetchImpl: typeof fetch,
): Promise<ILinkResult<string>> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetchImpl(inboundUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        apiVersion: "v1",
        fromUserId: input.fromUserId,
        content: input.content,
        messageId: input.messageId,
        projectId: "wechat",
      }),
      signal: ctrl.signal,
    })
    const raw = await res.text()
    if (!res.ok) {
      return { ok: false, reason: `inbound HTTP ${res.status}: ${raw.slice(0, 200)}` }
    }
    try {
      const parsed: unknown = JSON.parse(raw)
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        return { ok: false, reason: "inbound response is not a JSON object" }
      }
      const reply = (parsed as Record<string, unknown>)["reply"]
      if (typeof reply !== "string" || !reply) {
        return { ok: false, reason: "inbound response has no reply" }
      }
      return { ok: true, value: reply }
    } catch {
      return { ok: false, reason: "inbound returned non-JSON" }
    }
  } catch (err: unknown) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export function startIlinkPoller(
  config: IlinkPollerConfig,
  opts: {
    readonly fetch?: typeof fetch
    readonly logger?: IlinkPollerLogger
    readonly sleep?: (ms: number) => Promise<void>
  } = {},
): IlinkPollerHandle {
  const logger = opts.logger ?? defaultLogger
  const fetchImpl = opts.fetch ?? fetch
  const sleep = opts.sleep ?? delay
  const client: ILinkClientConfig = {
    baseUrl: config.baseUrl,
    token: config.token,
    fetch: fetchImpl,
    longPollTimeoutMs: config.longPollTimeoutMs,
  }
  const state: IlinkPollState = {
    syncBuf: loadSyncBuf(config.syncBufPath),
    seenIds: new Set(),
  }
  let stopped = false

  const tick = async (): Promise<void> => {
    if (stopped) return
    try {
      await runIlinkPollCycle(
        {
          getUpdates: (syncBuf) => ilinkGetUpdates(client, syncBuf),
          postInbound: (input) =>
            postInboundHttp(config.inboundUrl, config.inboundTimeoutMs, input, fetchImpl),
          sendMessage: (input) => ilinkSendMessage(client, input),
          accountId: config.accountId,
          emptyPollDelayMs: config.emptyPollDelayMs,
          sessionExpiredSleepMs: config.sessionExpiredSleepMs,
          sleep,
          dmPolicy: config.dmPolicy,
          allowedUserIds: config.allowedUserIds,
          dropGroups: config.dropGroups,
          persistSyncBuf: (syncBuf) => saveSyncBuf(config.syncBufPath, syncBuf),
        },
        state,
      )
    } catch (err: unknown) {
      logger.error("[ilink-poller] cycle failed:", err)
      await sleep(config.emptyPollDelayMs)
    }
    if (!stopped) {
      void tick()
    }
  }

  logger.warn(
    `[ilink-poller] started baseUrl=${config.baseUrl} inbound=${config.inboundUrl} dmPolicy=${config.dmPolicy}`,
  )
  void tick()
  return {
    stop: () => {
      stopped = true
    },
  }
}

export function startIlinkPollerIfEnabled(
  env: NodeJS.ProcessEnv,
  opts: {
    readonly fetch?: typeof fetch
    readonly logger?: IlinkPollerLogger
  } = {},
): IlinkPollerHandle | undefined {
  const parsed = parseIlinkPollerConfig(env)
  const logger = opts.logger ?? defaultLogger
  if (!parsed.ok) {
    logger.warn(`[ilink-poller] skipped: ${parsed.reason}`)
    return undefined
  }
  return startIlinkPoller(parsed.value, {
    logger,
    ...(opts.fetch ? { fetch: opts.fetch } : {}),
  })
}
