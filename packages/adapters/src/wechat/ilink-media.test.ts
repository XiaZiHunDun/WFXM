import { createCipheriv } from "node:crypto"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"
import { pkcs7Pad } from "./ilink-media-crypto.js"
import {
  downloadAndCacheIlinkMedia,
  enrichIlinkInboundContent,
  extractIlinkMediaRef,
} from "./ilink-media.js"

const CDN_HOST = "https://novac2c.cdn.wechat.qq.com/c2c/x.bin"
const KEY = Buffer.from("0123456789abcdef")

function encryptEcb(plain: Buffer): Buffer {
  const cipher = createCipheriv("aes-128-ecb", KEY, null)
  cipher.setAutoPadding(false)
  return Buffer.concat([cipher.update(pkcs7Pad(plain)), cipher.final()])
}

const dirs: string[] = []

function tmpCache(): string {
  const dir = mkdtempSync(join(tmpdir(), "ilink-media-"))
  dirs.push(dir)
  return dir
}

afterEach(() => {
  for (const dir of dirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

describe("extractIlinkMediaRef", () => {
  it("reads image_item media.encrypt_query_param and aeskey hex", () => {
    const ref = extractIlinkMediaRef([
      {
        type: 2,
        image_item: {
          aeskey: KEY.toString("hex"),
          media: { encrypt_query_param: "eqp-1" },
        },
      },
    ])
    expect(ref?.kind).toBe("image")
    expect(ref?.encryptQueryParam).toBe("eqp-1")
    expect(ref?.aesKeyB64).toBe(KEY.toString("base64"))
  })

  it("reads full_url from nested media", () => {
    const ref = extractIlinkMediaRef([
      {
        type: "file",
        file_item: {
          file_name: "notes.txt",
          media: { full_url: CDN_HOST, aes_key: KEY.toString("base64") },
        },
      },
    ])
    expect(ref?.kind).toBe("file")
    expect(ref?.fullUrl).toBe(CDN_HOST)
    expect(ref?.fileName).toBe("notes.txt")
  })
})

describe("downloadAndCacheIlinkMedia", () => {
  it("downloads, decrypts, and writes under cacheDir", async () => {
    const plain = Buffer.from("jpeg-bytes")
    const fetchMock = vi.fn(async () => new Response(encryptEcb(plain), { status: 200 }))
    const cacheDir = tmpCache()
    const result = await downloadAndCacheIlinkMedia(
      {
        kind: "image",
        fullUrl: CDN_HOST,
        aesKeyB64: KEY.toString("base64"),
      },
      {
        cacheDir,
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: fetchMock,
        maxBytes: 1024,
      },
    )
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(readFileSync(result.value.path).equals(plain)).toBe(true)
    expect(result.value.path.startsWith(cacheDir)).toBe(true)
  })

  it("rejects non-allowlisted full_url", async () => {
    const result = await downloadAndCacheIlinkMedia(
      { kind: "image", fullUrl: "https://evil.example/x" },
      {
        cacheDir: tmpCache(),
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: vi.fn(),
        maxBytes: 1024,
      },
    )
    expect(result.ok).toBe(false)
  })
})

describe("enrichIlinkInboundContent", () => {
  it("replaces image placeholder with saved path", async () => {
    const plain = Buffer.from("img")
    const fetchMock = vi.fn(async () => new Response(encryptEcb(plain), { status: 200 }))
    const cacheDir = tmpCache()
    const itemList = [
      { type: 2, image_item: { media: { full_url: CDN_HOST, aes_key: KEY.toString("base64") } } },
    ]
    const text = await enrichIlinkInboundContent(itemList, "[收到图片，当前版本暂不解析媒体]", {
      cacheDir,
      cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
      fetch: fetchMock,
      maxBytes: 1024,
    })
    expect(text).toMatch(/收到图片，已保存到 /)
    expect(text).toContain(cacheDir)
  })

  it("keeps placeholder when download fails", async () => {
    const fetchMock = vi.fn(async () => new Response("nope", { status: 500 }))
    const text = await enrichIlinkInboundContent(
      [{ type: 2, image_item: { media: { full_url: CDN_HOST } } }],
      "[收到图片，当前版本暂不解析媒体]",
      {
        cacheDir: tmpCache(),
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: fetchMock,
        maxBytes: 1024,
      },
    )
    expect(text).toBe("[收到图片，当前版本暂不解析媒体]")
  })

  it("uses WeChat voice transcript and does not download", async () => {
    const fetchMock = vi.fn(async () => new Response("nope", { status: 500 }))
    const text = await enrichIlinkInboundContent(
      [
        {
          type: 3,
          voice_item: {
            text: "明天开会",
            media: { full_url: CDN_HOST },
          },
        },
      ],
      "[收到语音，当前版本暂不解析媒体]",
      {
        cacheDir: tmpCache(),
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: fetchMock,
        maxBytes: 1024,
      },
    )
    expect(text).toBe("收到语音：明天开会")
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("appends ASR text when download succeeds and transcribeVoice returns ok", async () => {
    const plain = Buffer.from("silk-bytes")
    const fetchMock = vi.fn(async () => new Response(encryptEcb(plain), { status: 200 }))
    const cacheDir = tmpCache()
    const text = await enrichIlinkInboundContent(
      [{ type: 3, voice_item: { media: { full_url: CDN_HOST, aes_key: KEY.toString("base64") } } }],
      "[收到语音，当前版本暂不解析媒体]",
      {
        cacheDir,
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: fetchMock,
        maxBytes: 1024,
        transcribeVoice: async () => ({ ok: true, value: "语音内容" }),
      },
    )
    expect(text).toContain("收到语音转写：语音内容")
    expect(text).toContain(cacheDir)
  })

  it("keeps saved-path note when ASR fails", async () => {
    const plain = Buffer.from("silk-bytes")
    const fetchMock = vi.fn(async () => new Response(encryptEcb(plain), { status: 200 }))
    const cacheDir = tmpCache()
    const text = await enrichIlinkInboundContent(
      [{ type: 3, voice_item: { media: { full_url: CDN_HOST, aes_key: KEY.toString("base64") } } }],
      "[收到语音，当前版本暂不解析媒体]",
      {
        cacheDir,
        cdnBaseUrl: "https://novac2c.cdn.weixin.qq.com/c2c",
        fetch: fetchMock,
        maxBytes: 1024,
        transcribeVoice: async () => ({ ok: false, reason: "silk decode is not bundled" }),
      },
    )
    expect(text).toMatch(/收到语音，已保存到 /)
    expect(text).not.toContain("转写")
  })
})
