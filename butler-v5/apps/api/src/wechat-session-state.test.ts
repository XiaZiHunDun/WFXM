import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import {
  readWechatSessionState,
  wechatSessionStatePath,
  writeWechatSessionState,
  type SessionState,
} from "./wechat-session-state.js"

describe("wechat-session-state", () => {
  let storeDir = ""
  let env: NodeJS.ProcessEnv

  beforeEach(() => {
    storeDir = mkdtempSync(join(tmpdir(), "butler-session-state-"))
    env = { BUTLER_V5_WECHAT_SESSION_STATE: join(storeDir, "session.json") }
  })

  afterEach(() => {
    if (storeDir) rmSync(storeDir, { recursive: true, force: true })
  })

  it("readWechatSessionState returns null when no file exists", () => {
    expect(readWechatSessionState("u-1", env)).toBeNull()
  })

  it("writeWechatSessionState + readWechatSessionState roundtrip preserves fields", () => {
    const state: SessionState = {
      openTaskCount: 3,
      candidateCount: 5,
      lastRunStatus: "success",
      lastReplyAt: 1_700_000_000_000,
    }
    writeWechatSessionState("u-1", state, env)
    expect(readWechatSessionState("u-1", env)).toEqual(state)
  })

  it("isolates state across multiple users in the same store", () => {
    writeWechatSessionState("u-1", {
      openTaskCount: 1,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: 100,
    }, env)
    writeWechatSessionState("u-2", {
      openTaskCount: 99,
      candidateCount: 7,
      lastRunStatus: "fail",
      lastReplyAt: 200,
    }, env)
    expect(readWechatSessionState("u-1", env)?.openTaskCount).toBe(1)
    expect(readWechatSessionState("u-2", env)?.openTaskCount).toBe(99)
    expect(readWechatSessionState("u-2", env)?.lastRunStatus).toBe("fail")
  })

  it("atomic write: no .tmp file left behind after success", () => {
    const path = wechatSessionStatePath(env)
    writeWechatSessionState("u-1", {
      openTaskCount: 0,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: 0,
    }, env)
    // The final store should exist; the temp file should not.
    expect(existsSync(path)).toBe(true)
    expect(existsSync(`${path}.tmp`)).toBe(false)
  })

  it("graceful degradation: corrupted JSON returns empty store", () => {
    const path = wechatSessionStatePath(env)
    writeFileSync(path, "not-json{", "utf8")
    expect(readWechatSessionState("u-1", env)).toBeNull()
  })

  it("graceful degradation: missing/wrong fields default sensibly", () => {
    const path = wechatSessionStatePath(env)
    writeFileSync(path, JSON.stringify({ "u-1": { lastReplyAt: 100 } }), "utf8")
    const s = readWechatSessionState("u-1", env)
    expect(s?.lastReplyAt).toBe(100)
    expect(s?.openTaskCount).toBeNull()
    expect(s?.candidateCount).toBeNull()
    expect(s?.lastRunStatus).toBe("none")
  })

  it("write replaces existing state for same user (no duplication)", () => {
    writeWechatSessionState("u-1", {
      openTaskCount: 1,
      candidateCount: 0,
      lastRunStatus: "none",
      lastReplyAt: 100,
    }, env)
    writeWechatSessionState("u-1", {
      openTaskCount: 5,
      candidateCount: 0,
      lastRunStatus: "success",
      lastReplyAt: 200,
    }, env)
    const s = readWechatSessionState("u-1", env)
    expect(s?.openTaskCount).toBe(5)
    expect(s?.lastReplyAt).toBe(200)
  })
})
