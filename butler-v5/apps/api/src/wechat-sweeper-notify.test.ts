import { afterEach, describe, expect, it } from "vitest"
import {
  _peekSweeperThrottleForTests,
  formatAutoPromoteNotify,
  formatCandidateExpiresNotify,
  isSweeperNotifyEnabled,
  pushSweeperNotify,
  resetSweeperThrottleForTests,
  resolveSweeperNotifyOwner,
  sweeperNotifyThrottleMs,
} from "./wechat-sweeper-notify.js"

describe("wechat-sweeper-notify", () => {
  afterEach(() => {
    resetSweeperThrottleForTests()
  })

  describe("env gating", () => {
    it("isSweeperNotifyEnabled: defaults to false", () => {
      expect(isSweeperNotifyEnabled({})).toBe(false)
    })

    it("isSweeperNotifyEnabled: true when BUTLER_V5_SWEEPER_NOTIFY_ENABLED=1", () => {
      expect(isSweeperNotifyEnabled({ BUTLER_V5_SWEEPER_NOTIFY_ENABLED: "1" })).toBe(
        true,
      )
    })

    it("resolveSweeperNotifyOwner: returns null when env unset", () => {
      expect(resolveSweeperNotifyOwner({})).toBeNull()
    })

    it("resolveSweeperNotifyOwner: returns trimmed value when set", () => {
      expect(
        resolveSweeperNotifyOwner({ BUTLER_V5_SWEEPER_NOTIFY_OWNER: "  owner-1  " }),
      ).toBe("owner-1")
    })
  })

  describe("throttle default + override", () => {
    it("default 1h", () => {
      expect(sweeperNotifyThrottleMs({})).toBe(60 * 60 * 1000)
    })

    it("env override (ms)", () => {
      expect(
        sweeperNotifyThrottleMs({ BUTLER_V5_SWEEPER_NOTIFY_THROTTLE_MS: "5000" }),
      ).toBe(5000)
    })

    it("invalid → default", () => {
      expect(
        sweeperNotifyThrottleMs({ BUTLER_V5_SWEEPER_NOTIFY_THROTTLE_MS: "garbage" }),
      ).toBe(60 * 60 * 1000)
    })
  })

  describe("format helpers", () => {
    it("candidate_expires: 0 expired → empty (skip push)", () => {
      expect(
        formatCandidateExpiresNotify({ expired: 0, scanned: 5 }),
      ).toBe("")
    })

    it("candidate_expires: N expired → digest with N + scanned", () => {
      const t = formatCandidateExpiresNotify({ expired: 7, scanned: 20 })
      expect(t).toContain("7 条候选已自动过期")
      expect(t).toContain("扫描 20 条")
    })

    it("auto_promote: 0 promoted → empty", () => {
      expect(formatAutoPromoteNotify({ promoted: 0, scanned: 5 })).toBe("")
    })

    it("auto_promote: N promoted → digest with N + scanned", () => {
      const t = formatAutoPromoteNotify({ promoted: 3, scanned: 12 })
      expect(t).toContain("3 条候选已自动升级")
      expect(t).toContain("扫描 12 条")
    })
  })

  describe("pushSweeperNotify", () => {
    const enabledEnv = {
      BUTLER_V5_SWEEPER_NOTIFY_ENABLED: "1",
      BUTLER_V5_WECHAT_SESSION_STATE: "/dev/null", // ignored
    }

    it("returns sent=false when disabled", async () => {
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "hello",
        env: {},
      })
      expect(result).toEqual({ sent: false, reason: "disabled" })
    })

    it("returns sent=false when text empty", async () => {
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "",
        env: enabledEnv,
      })
      expect(result).toEqual({ sent: false, reason: "empty text" })
    })

    it("returns sent=false when owner empty", async () => {
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "   ",
        text: "hello",
        env: enabledEnv,
      })
      expect(result).toEqual({ sent: false, reason: "no owner" })
    })

    it("calls send on first push within window; records throttle", async () => {
      let sent: { to: string; text: string } | null = null
      const fakeSend = async (a: { to: string; text: string }) => {
        sent = { to: a.to, text: a.text }
        return { ok: true as const }
      }
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-1",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      expect(result).toEqual({ sent: true })
      expect(sent).toEqual({ to: "u-1", text: "msg-1" })
      expect(_peekSweeperThrottleForTests("candidate_expires:u-1")).toBe(1000)
    })

    it("throttles second push within 1h", async () => {
      const fakeSend = async () => ({ ok: true as const })
      await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-1",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-2",
        env: enabledEnv,
        now: 1000 + 30 * 60 * 1000, // 30 min later
        send: fakeSend,
      })
      expect(result).toEqual({ sent: false, reason: "throttled" })
    })

    it("allows push after throttle window expires", async () => {
      const fakeSend = async () => ({ ok: true as const })
      await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-1",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      const result = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-2",
        env: enabledEnv,
        now: 1000 + 61 * 60 * 1000, // 61 min later
        send: fakeSend,
      })
      expect(result).toEqual({ sent: true })
    })

    it("throttle is per (type, owner) — D40 and D42 push independently", async () => {
      const fakeSend = async () => ({ ok: true as const })
      // D40 push
      await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "d40-1",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      // D42 push 5 min later — should NOT be throttled (different type key)
      const r = await pushSweeperNotify({
        type: "auto_promote",
        to: "u-1",
        text: "d42-1",
        env: enabledEnv,
        now: 1000 + 5 * 60 * 1000,
        send: fakeSend,
      })
      expect(r).toEqual({ sent: true })
    })

    it("send failure records throttle so persistent errors don't per-tick spam (D55 SF-04)", async () => {
      const fakeSend = async () => ({ ok: false as const, reason: "ilink down" })
      const r1 = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-1",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      expect(r1).toEqual({ sent: false, reason: "ilink down" })
      // Throttle IS recorded on failure (audit D55 SF-04): next push within
      // the throttle window must short-circuit, not burn through the same
      // outage. Owner can still bypass via /记忆候选 command path.
      expect(_peekSweeperThrottleForTests("candidate_expires:u-1")).toBe(1000)
      const r2 = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-2",
        env: enabledEnv,
        now: 1000 + 60 * 1000, // 1 min later, well inside 1h window
        send: fakeSend,
      })
      expect(r2).toEqual({ sent: false, reason: "throttled" })
    })

    it("send throw also records throttle (D55 SF-04 backoff)", async () => {
      const throwing = async () => {
        throw new Error("kaboom")
      }
      const r = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-1",
        env: enabledEnv,
        now: 1000,
        send: throwing,
      })
      expect(r).toEqual({ sent: false, reason: "kaboom" })
      expect(_peekSweeperThrottleForTests("candidate_expires:u-1")).toBe(1000)
      // Next push 1 min later is throttled, not retried.
      const r2 = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "msg-2",
        env: enabledEnv,
        now: 1000 + 60 * 1000,
        send: throwing,
      })
      expect(r2).toEqual({ sent: false, reason: "throttled" })
    })

    it("different owners don't share throttle", async () => {
      const fakeSend = async () => ({ ok: true as const })
      await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-1",
        text: "m",
        env: enabledEnv,
        now: 1000,
        send: fakeSend,
      })
      const r = await pushSweeperNotify({
        type: "candidate_expires",
        to: "u-2",
        text: "m",
        env: enabledEnv,
        now: 1000 + 5 * 60 * 1000,
        send: fakeSend,
      })
      expect(r).toEqual({ sent: true })
    })
  })
})
