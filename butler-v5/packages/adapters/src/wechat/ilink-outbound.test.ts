import { describe, expect, it, vi } from "vitest"
import { DEFAULT_WECHAT_CDN_BASE_URL } from "./ilink-media.js"
import {
  EP_GET_UPLOAD_URL,
  ITEM_FILE,
  ITEM_IMAGE,
  MEDIA_TYPE_FILE,
  MEDIA_TYPE_IMAGE,
  classifyOutboundMedia,
} from "./ilink-protocol.js"
import { sendOutboundMedia } from "./ilink-outbound.js"

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

describe("classifyOutboundMedia", () => {
  it("treats jpeg/png as image and everything else as file", () => {
    expect(classifyOutboundMedia("photo.JPG")).toBe("image")
    expect(classifyOutboundMedia("a.png")).toBe("image")
    expect(classifyOutboundMedia("notes.txt")).toBe("file")
    expect(classifyOutboundMedia("clip.mp4")).toBe("file")
  })
})

describe("sendOutboundMedia", () => {
  it("uploads a jpeg then sendmessage with image item type=2", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith(`/${EP_GET_UPLOAD_URL}`)) {
        const body = JSON.parse(String(init?.body)) as {
          media_type: number
          to_user_id: string
        }
        expect(body.media_type).toBe(MEDIA_TYPE_IMAGE)
        expect(body.to_user_id).toBe("u-wx")
        return jsonResponse({
          ret: 0,
          upload_full_url: "https://novac2c.cdn.weixin.qq.com/c2c/upload",
        })
      }
      if (url.includes("/upload")) {
        expect(init?.method).toBe("POST")
        expect((init?.headers as Record<string, string>)["Content-Type"]).toBe(
          "application/octet-stream",
        )
        return new Response("", {
          status: 200,
          headers: { "x-encrypted-param": "eqp-out" },
        })
      }
      if (url.endsWith("/ilink/bot/sendmessage")) {
        const body = JSON.parse(String(init?.body)) as {
          msg: { item_list: { type: number; image_item?: { mid_size: number } }[] }
        }
        expect(body.msg.item_list[0]?.type).toBe(ITEM_IMAGE)
        expect(body.msg.item_list[0]?.image_item?.mid_size).toBeGreaterThan(0)
        return jsonResponse({ ret: 0, errcode: 0 })
      }
      return jsonResponse({ ret: -1 }, 500)
    })

    const result = await sendOutboundMedia(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      {
        to: "u-wx",
        fileName: "photo.jpg",
        plaintext: Buffer.from([0xff, 0xd8, 0xff, 0xd9, 0x00, 0x01]),
        cdnBaseUrl: DEFAULT_WECHAT_CDN_BASE_URL,
        maxBytes: 8 * 1024 * 1024,
      },
    )
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.value.kind).toBe("image")
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it("sends a .txt as file item type=4 using upload_param fallback", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith(`/${EP_GET_UPLOAD_URL}`)) {
        const body = JSON.parse(String(init?.body)) as { media_type: number }
        expect(body.media_type).toBe(MEDIA_TYPE_FILE)
        return jsonResponse({ ret: 0, upload_param: "up-param-1" })
      }
      if (url.includes("encrypted_query_param=") && url.includes("filekey=")) {
        return new Response("", {
          status: 200,
          headers: { "x-encrypted-param": "eqp-file" },
        })
      }
      if (url.endsWith("/ilink/bot/sendmessage")) {
        const body = JSON.parse(String(init?.body)) as {
          msg: {
            item_list: { type: number; file_item?: { file_name: string } }[]
          }
        }
        expect(body.msg.item_list[0]?.type).toBe(ITEM_FILE)
        expect(body.msg.item_list[0]?.file_item?.file_name).toBe("notes.txt")
        return jsonResponse({ ret: 0 })
      }
      return jsonResponse({ ret: -1 }, 500)
    })

    const result = await sendOutboundMedia(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      {
        to: "u-wx",
        fileName: "notes.txt",
        plaintext: Buffer.from("hello file"),
        cdnBaseUrl: DEFAULT_WECHAT_CDN_BASE_URL,
        maxBytes: 8 * 1024 * 1024,
      },
    )
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.value.kind).toBe("file")
  })

  it("rejects an oversize payload without fetching", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ret: 0 }))
    const result = await sendOutboundMedia(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      {
        to: "u-wx",
        fileName: "big.jpg",
        plaintext: Buffer.alloc(64),
        cdnBaseUrl: DEFAULT_WECHAT_CDN_BASE_URL,
        maxBytes: 16,
      },
    )
    expect(result.ok).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("rejects a CDN host that is not on the WeChat allowlist", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith(`/${EP_GET_UPLOAD_URL}`)) {
        return jsonResponse({
          ret: 0,
          upload_full_url: "https://evil.example/upload",
        })
      }
      return jsonResponse({ ret: 0 })
    })
    const result = await sendOutboundMedia(
      { baseUrl: "http://ilink.test", token: "tok", fetch: fetchMock as unknown as typeof fetch },
      {
        to: "u-wx",
        fileName: "photo.jpg",
        plaintext: Buffer.from("img"),
        cdnBaseUrl: DEFAULT_WECHAT_CDN_BASE_URL,
        maxBytes: 8 * 1024 * 1024,
      },
    )
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain("not a WeChat CDN")
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
