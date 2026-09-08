import { mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { writeWechatSessionState, type SessionState } from "./wechat-session-state.js"
import {
  buildSessionOpenDigest,
  maybePrependSessionDigest,
  sessionDigestIdleMs,
} from "./wechat-session-digest.js"

const ONE_MIN = 60_000
const ONE_HOUR = 60 * ONE_MIN

describe("wechat-session-digest", () => {
  let storeDir = ""
  let env: NodeJS.ProcessEnv

  beforeEach(() => {
    storeDir = mkdtempSync(join(tmpdir(), "butler-session-digest-"))
    env = { BUTLER_V5_WECHAT_SESSION_STATE: join(storeDir, "session.json") }
  })

  afterEach(() => {
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("returns null when no snapshot exists", () => {
    expect(
      buildSessionOpenDigest({ userId: "u-1", now: Date.now(), env }),
    ).toBeNull()
  })

  it("returns null when last reply is within the idle window (30 min default)", () => {
    const now = 1_000_000
    const state: SessionState = {
      openTaskCount: 3,
      candidateCount: 5,
      lastRunStatus: "success",
      lastReplyAt: now - 5 * ONE_MIN, // 5 min ago
    }
    writeWechatSessionState("u-1", state, env)
    expect(buildSessionOpenDigest({ userId: "u-1", now, env })).toBeNull()
  })

  it("returns digest when last reply is older than idle window", () => {
    const now = 1_000_000
    const state: SessionState = {
      openTaskCount: 3,
      candidateCount: 5,
      lastRunStatus: "success",
      lastReplyAt: now - 45 * ONE_MIN, // 45 min ago
    }
    writeWechatSessionState("u-1", state, env)
    const digest = buildSessionOpenDigest({ userId: "u-1", now, env })
    expect(digest).not.toBeNull()
    expect(digest?.text).toContain("3 任务在跑")
    expect(digest?.text).toContain("5 候选待审")
    expect(digest?.text).toContain("0 失败")
    expect(digest?.text).toContain("约 45m 前")
  })

  it("failed run renders as '1 失败'", () => {
    const now = 1_000_000
    writeWechatSessionState("u-1", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "fail",
      lastReplyAt: now - ONE_HOUR,
    }, env)
    const digest = buildSessionOpenDigest({ userId: "u-1", now, env })
    expect(digest?.text).toContain("1 失败")
  })

  it("null counts render as '?'", () => {
    const now = 1_000_000
    writeWechatSessionState("u-1", {
      openTaskCount: null,
      candidateCount: null,
      lastRunStatus: "none",
      lastReplyAt: now - ONE_HOUR,
    }, env)
    const digest = buildSessionOpenDigest({ userId: "u-1", now, env })
    expect(digest?.text).toContain("? 任务在跑")
    expect(digest?.text).toContain("? 候选待审")
  })

  it("elapsed formatter: hours and days", () => {
    const now = 1_000_000
    writeWechatSessionState("u-1", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: now - 3 * ONE_HOUR, // 3h ago
    }, env)
    const digest = buildSessionOpenDigest({ userId: "u-1", now, env })
    expect(digest?.text).toContain("约 3h 前")

    writeWechatSessionState("u-2", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: now - 26 * ONE_HOUR, // ~1d ago
    }, env)
    const d2 = buildSessionOpenDigest({ userId: "u-2", now, env })
    expect(d2?.text).toContain("约 1d 前")
  })

  it("env override: BUTLER_V5_SESSION_DIGEST_IDLE_MS shortens threshold", () => {
    const now = 1_000_000
    const shortEnv = {
      ...env,
      BUTLER_V5_SESSION_DIGEST_IDLE_MS: String(2 * ONE_MIN), // 2 min
    }
    expect(sessionDigestIdleMs(shortEnv)).toBe(2 * ONE_MIN)
    // With 2-min threshold, a 5-min-old snapshot should produce a digest
    writeWechatSessionState("u-1", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: now - 5 * ONE_MIN,
    }, shortEnv)
    const digest = buildSessionOpenDigest({ userId: "u-1", now, env: shortEnv })
    expect(digest).not.toBeNull()
  })

  it("default threshold is 30 min when env is missing/invalid", () => {
    expect(sessionDigestIdleMs(env)).toBe(30 * ONE_MIN)
    expect(sessionDigestIdleMs({ ...env, BUTLER_V5_SESSION_DIGEST_IDLE_MS: "garbage" })).toBe(
      30 * ONE_MIN,
    )
    expect(sessionDigestIdleMs({ ...env, BUTLER_V5_SESSION_DIGEST_IDLE_MS: "-1" })).toBe(
      30 * ONE_MIN,
    )
  })

  it("maybePrependSessionDigest: no snapshot → reply unchanged", () => {
    const out = maybePrependSessionDigest({
      reply: "hello world",
      userId: "u-noop",
      now: Date.now(),
      env,
    })
    expect(out.reply).toBe("hello world")
    expect(out.digest).toBeNull()
  })

  it("maybePrependSessionDigest: 5 min ago → reply unchanged", () => {
    const now = 1_000_000
    writeWechatSessionState("u-fresh", {
      openTaskCount: 1,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: now - 5 * ONE_MIN,
    }, env)
    const out = maybePrependSessionDigest({
      reply: "fresh reply",
      userId: "u-fresh",
      now,
      env,
    })
    expect(out.reply).toBe("fresh reply")
    expect(out.digest).toBeNull()
  })

  it("maybePrependSessionDigest: 30 min ago → digest prepended with \\n\\n", () => {
    const now = 1_000_000
    writeWechatSessionState("u-stale", {
      openTaskCount: 2,
      candidateCount: 4,
      lastRunStatus: "success",
      lastReplyAt: now - 45 * ONE_MIN,
    }, env)
    const out = maybePrependSessionDigest({
      reply: "stale reply",
      userId: "u-stale",
      now,
      env,
    })
    expect(out.digest).not.toBeNull()
    expect(out.reply).toMatch(/^【上次您离开时】.*\n\nstale reply$/)
    expect(out.reply).toContain("2 任务在跑")
    expect(out.reply).toContain("4 候选待审")
    expect(out.reply).toContain("0 失败")
  })

  it("maybePrependSessionDigest: failed run shows '1 失败'", () => {
    const now = 1_000_000
    writeWechatSessionState("u-fail", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "fail",
      lastReplyAt: now - ONE_HOUR,
    }, env)
    const out = maybePrependSessionDigest({
      reply: "ok",
      userId: "u-fail",
      now,
      env,
    })
    expect(out.reply).toContain("1 失败")
  })
})
