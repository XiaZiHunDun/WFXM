import { afterEach, describe, expect, it } from "vitest"
import { Hono } from "hono"
import { createHmac } from "node:crypto"
import { createRoutes } from "./routes.js"

function signSlack(secret: string, ts: string, raw: string): string {
  return `v0=${createHmac("sha256", secret).update(`v0:${ts}:${raw}`).digest("hex")}`
}

function buildApp() {
  const app = new Hono()
  // Same shape as existing routes.test.ts — wiring type assertion. Real
  // tests of message → Run Engine path live elsewhere (Owner real e2e).
  createRoutes(app, { eventStore: null as never })
  return app
}

describe("Slack HTTP route guards (test-env e2e)", () => {
  const originalEnv = {
    enabled: process.env["BUTLER_V5_SLACK_ENABLED"],
    secret: process.env["BUTLER_V5_SLACK_SIGNING_SECRET"],
  }

  afterEach(() => {
    if (originalEnv.enabled === undefined) delete process.env["BUTLER_V5_SLACK_ENABLED"]
    else process.env["BUTLER_V5_SLACK_ENABLED"] = originalEnv.enabled
    if (originalEnv.secret === undefined) delete process.env["BUTLER_V5_SLACK_SIGNING_SECRET"]
    else process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] = originalEnv.secret
  })

  it("returns 404 when Slack channel disabled (no BUTLER_V5_SLACK_ENABLED)", async () => {
    delete process.env["BUTLER_V5_SLACK_ENABLED"]
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      body: "{}",
    })
    expect(res.status).toBe(404)
  })

  it("returns 401 with invalid signing signature (wrong secret)", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] = "real-secret"
    // D63 T4 (audit #9 F-01) post-fix: Slack url_verification is the
    // documented exception that skips signature check (per Slack
    // onboarding handshake). To test signature FAIL-CLOSED, send an
    // event_callback body which must be signature-verified.
    const body = JSON.stringify({
      type: "event_callback",
      event: { type: "message", user: "u1", text: "hi" },
    })
    const wrongSig = signSlack("attacker-secret", "1700000000", body)
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-slack-signature": wrongSig,
        "x-slack-request-timestamp": "1700000000",
      },
      body,
    })
    expect(res.status).toBe(401)
  })

  it("returns 401 with tampered body", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] = "real-secret"
    // D63 T4 post-fix: signature check applies to non-challenge events.
    const signedBody = JSON.stringify({
      type: "event_callback",
      event: { type: "message", user: "u1", text: "hi" },
    })
    const sig = signSlack("real-secret", "1700000000", signedBody)
    const tamperedBody = JSON.stringify({
      type: "event_callback",
      event: { type: "message", user: "u1", text: "DIFFERENT" },
    })
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-slack-signature": sig,
        "x-slack-request-timestamp": "1700000000",
      },
      body: tamperedBody,
    })
    expect(res.status).toBe(401)
  })

  it("returns 401 with expired timestamp (>5 min replay window)", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] = "real-secret"
    const oldTs = "1700000000"
    const nowMs = Number(oldTs) * 1000 + 6 * 60_000 // 6 min later
    // D63 T4 post-fix: signature check applies to non-challenge events.
    const body = JSON.stringify({
      type: "event_callback",
      event: { type: "message", user: "u1", text: "hi" },
    })
    const sig = signSlack("real-secret", oldTs, body)
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-slack-signature": sig,
        "x-slack-request-timestamp": oldTs,
      },
      body,
    })
    // The Date.now() at test time is far past 1700000000 (~ 2023), so this WILL be >5min stale
    expect(res.status).toBe(401)
    expect(nowMs).toBeGreaterThan(Number(oldTs) * 1000 + 5 * 60_000)
  })

  it("returns challenge for url_verification when signature is valid", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    process.env["BUTLER_V5_SLACK_SIGNING_SECRET"] = "real-secret"
    const body = JSON.stringify({ type: "url_verification", challenge: "verify-me" })
    const ts = String(Math.floor(Date.now() / 1000))
    const sig = signSlack("real-secret", ts, body)
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-slack-signature": sig,
        "x-slack-request-timestamp": ts,
      },
      body,
    })
    expect(res.status).toBe(200)
    const json = (await res.json()) as { challenge: string }
    expect(json.challenge).toBe("verify-me")
  })

  it("rejects unsigned event_callback when BUTLER_V5_SLACK_SIGNING_SECRET is empty (FAIL-CLOSED)", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    delete process.env["BUTLER_V5_SLACK_SIGNING_SECRET"]
    // D63 T4 (audit #9 F-01) post-fix: FAIL-CLOSED on empty secret for
    // non-challenge events. url_verification still bypasses signature
    // check (per Slack protocol); this test exercises the event_callback
    // FAIL-CLOSED branch.
    const body = JSON.stringify({
      type: "event_callback",
      event: { type: "message", user: "u1", text: "hi" },
    })
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
    })
    expect(res.status).toBe(401)
  })

  it("returns 400 for invalid JSON body", async () => {
    process.env["BUTLER_V5_SLACK_ENABLED"] = "1"
    delete process.env["BUTLER_V5_SLACK_SIGNING_SECRET"]
    const res = await buildApp().request("/v1/channel/slack/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "not json {",
    })
    expect(res.status).toBe(400)
  })
})