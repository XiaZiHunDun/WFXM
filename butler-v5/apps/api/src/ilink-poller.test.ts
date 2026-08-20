import { describe, expect, it } from "vitest"
import { inboundFromIlinkMsg, SESSION_EXPIRED_ERRCODE } from "@butler/adapters"
import { parseIlinkPollerConfig } from "./ilink-config.js"
import { runIlinkPollCycle, type IlinkPollState } from "./ilink-poller.js"

describe("parseIlinkPollerConfig", () => {
  it("stays off unless BUTLER_V5_ILINK_ENABLED is set", () => {
    const parsed = parseIlinkPollerConfig({ WECHAT_TOKEN: "tok" })
    expect(parsed.ok).toBe(false)
  })

  it("requires WECHAT_TOKEN when enabled", () => {
    const parsed = parseIlinkPollerConfig({ BUTLER_V5_ILINK_ENABLED: "1" })
    expect(parsed.ok).toBe(false)
  })

  it("reads WECHAT_BASE_URL and default inbound URL", () => {
    const parsed = parseIlinkPollerConfig({
      BUTLER_V5_ILINK_ENABLED: "1",
      WECHAT_TOKEN: "tok",
      WECHAT_BASE_URL: "http://127.0.0.1:9999",
      PORT: "3000",
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.value.baseUrl).toBe("http://127.0.0.1:9999")
    expect(parsed.value.inboundUrl).toBe("http://127.0.0.1:3000/v1/wechat/inbound")
    expect(parsed.value.token).toBe("tok")
  })

  it("parses allowlist policy and owner id", () => {
    const parsed = parseIlinkPollerConfig({
      BUTLER_V5_ILINK_ENABLED: "1",
      WECHAT_TOKEN: "tok",
      WECHAT_DM_POLICY: "allowlist",
      WECHAT_ALLOWED_USERS: "u-a,u-b",
      BUTLER_OWNER_WECHAT_ID: "u-owner",
    })
    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.value.dmPolicy).toBe("allowlist")
    expect(parsed.value.allowedUserIds).toEqual(["u-a", "u-b", "u-owner"])
    expect(parsed.value.dropGroups).toBe(true)
  })
})

describe("runIlinkPollCycle", () => {
  it("forwards text to inbound and sendmessage", async () => {
    const inboundCalls: unknown[] = []
    const sendCalls: unknown[] = []
    const state: IlinkPollState = { syncBuf: "", seenIds: new Set() }
    const stats = await runIlinkPollCycle(
      {
        getUpdates: async () => ({
          ok: true,
          value: {
            ret: 0,
            get_updates_buf: "b2",
            msgs: [
              {
                msg_id: "m1",
                from_user_id: "u-wx",
                context_token: "ct",
                item_list: [{ type: "text", text_item: { content: "喝茶" } }],
              },
            ],
          },
        }),
        postInbound: async (input) => {
          inboundCalls.push(input)
          return { ok: true, value: "好的，喝茶" }
        },
        sendMessage: async (input) => {
          sendCalls.push(input)
          return { ok: true, value: {} }
        },
        accountId: "bot-self",
        emptyPollDelayMs: 0,
        sessionExpiredSleepMs: 0,
        sleep: async () => undefined,
      },
      state,
    )
    expect(stats).toEqual({
      processed: 1,
      sent: 1,
      skipped: 0,
      expired: false,
      empty: false,
    })
    expect(state.syncBuf).toBe("b2")
    expect(inboundCalls).toEqual([{ fromUserId: "u-wx", content: "喝茶", messageId: "m1" }])
    expect(sendCalls).toEqual([{ to: "u-wx", text: "好的，喝茶", contextToken: "ct" }])
    expect(inboundFromIlinkMsg(undefined)).toBeUndefined()
  })

  it("skips the bot's own account id and empty polls", async () => {
    const state: IlinkPollState = { syncBuf: "a", seenIds: new Set() }
    const empty = await runIlinkPollCycle(
      {
        getUpdates: async () => ({
          ok: true,
          value: { ret: 0, msgs: [], get_updates_buf: "a" },
        }),
        postInbound: async () => ({ ok: true, value: "x" }),
        sendMessage: async () => ({ ok: true, value: {} }),
        accountId: "bot-self",
        emptyPollDelayMs: 0,
        sessionExpiredSleepMs: 0,
        sleep: async () => undefined,
      },
      state,
    )
    expect(empty.empty).toBe(true)

    const skipped = await runIlinkPollCycle(
      {
        getUpdates: async () => ({
          ok: true,
          value: {
            ret: 0,
            msgs: [
              {
                msg_id: "m2",
                from_user_id: "bot-self",
                item_list: [{ type: "text", text_item: { content: "echo" } }],
              },
            ],
          },
        }),
        postInbound: async () => ({ ok: true, value: "x" }),
        sendMessage: async () => ({ ok: true, value: {} }),
        accountId: "bot-self",
        emptyPollDelayMs: 0,
        sessionExpiredSleepMs: 0,
        sleep: async () => undefined,
      },
      state,
    )
    expect(skipped.processed).toBe(0)
    expect(skipped.skipped).toBe(1)
  })

  it("sleeps on session expired", async () => {
    let slept = 0
    const stats = await runIlinkPollCycle(
      {
        getUpdates: async () => ({
          ok: true,
          value: { ret: SESSION_EXPIRED_ERRCODE, errcode: SESSION_EXPIRED_ERRCODE },
        }),
        postInbound: async () => ({ ok: true, value: "x" }),
        sendMessage: async () => ({ ok: true, value: {} }),
        accountId: "",
        emptyPollDelayMs: 0,
        sessionExpiredSleepMs: 7,
        sleep: async (ms) => {
          slept = ms
        },
      },
      { syncBuf: "", seenIds: new Set() },
    )
    expect(stats.expired).toBe(true)
    expect(slept).toBe(7)
  })

  it("drops group chats and allowlist misses", async () => {
    const inboundCalls: string[] = []
    const stats = await runIlinkPollCycle(
      {
        getUpdates: async () => ({
          ok: true,
          value: {
            ret: 0,
            msgs: [
              {
                msg_id: "g1",
                from_user_id: "u-friend",
                room_id: "room-9",
                item_list: [{ type: "text", text_item: { content: "群消息" } }],
              },
              {
                msg_id: "d1",
                from_user_id: "u-stranger",
                item_list: [{ type: "text", text_item: { content: "私聊" } }],
              },
              {
                msg_id: "d2",
                from_user_id: "u-owner",
                item_list: [{ type: "text", text_item: { content: "主人" } }],
              },
            ],
          },
        }),
        postInbound: async (input) => {
          inboundCalls.push(input.fromUserId)
          return { ok: true, value: "ok" }
        },
        sendMessage: async () => ({ ok: true, value: {} }),
        accountId: "bot-self",
        emptyPollDelayMs: 0,
        sessionExpiredSleepMs: 0,
        sleep: async () => undefined,
        dmPolicy: "allowlist",
        allowedUserIds: ["u-owner"],
        dropGroups: true,
      },
      { syncBuf: "", seenIds: new Set() },
    )
    expect(stats.processed).toBe(1)
    expect(stats.skipped).toBe(2)
    expect(inboundCalls).toEqual(["u-owner"])
  })
})
