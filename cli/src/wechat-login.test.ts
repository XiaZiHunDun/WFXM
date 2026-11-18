import { mkdtempSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { describe, expect, it, vi } from "vitest"
import { runWechatLogin } from "./wechat-login.js"

describe("runWechatLogin", () => {
  it("writes env after QR confirmed", async () => {
    const dir = mkdtempSync(join(tmpdir(), "butler-v5-login-"))
    const envPath = join(dir, "env")
    const fetchMock = vi.fn(async (url: string | URL) => {
      const href = String(url)
      if (href.includes("get_bot_qrcode")) {
        return new Response(
          JSON.stringify({ qrcode: "hex-1", qrcode_img_content: "https://scan.example/qr" }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({
          status: "confirmed",
          ilink_bot_id: "bot-acc",
          bot_token: "tok-acc",
          baseurl: "https://ilinkai.weixin.qq.com",
          ilink_user_id: "u-1",
        }),
        { status: 200 },
      )
    })
    const logs: string[] = []
    const result = await runWechatLogin({
      envPath,
      fetch: fetchMock as unknown as typeof fetch,
      timeoutMs: 5_000,
      pollMs: 1,
      sleep: async () => undefined,
      log: (msg) => logs.push(msg),
    })
    expect(result).toEqual({ ok: true, accountId: "bot-acc" })
    expect(logs.join("\n")).toContain("https://scan.example/qr")
    expect(logs.join("\n")).not.toContain("tok-acc")
    const { readFileSync } = await import("node:fs")
    expect(readFileSync(envPath, "utf8")).toContain("WECHAT_TOKEN=tok-acc")
    expect(readFileSync(envPath, "utf8")).toContain("WECHAT_ACCOUNT_ID=bot-acc")
  })
})
