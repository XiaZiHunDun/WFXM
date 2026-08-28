import { describe, expect, it, vi } from "vitest"
import { describeSlackFiles } from "@butler/adapters/slack/index.js"
import {
  describeTelegramMedia,
  downloadTelegramFile,
  enrichTelegramMediaContent,
} from "./channel-media.js"

describe("channel media", () => {
  it("describes slack file attachments", () => {
    const parsed = describeSlackFiles(
      [{ name: "diagram.png", mimetype: "image/png", size: 1024 }],
      "see this",
    )
    expect(parsed?.content).toContain("see this")
    expect(parsed?.content).toContain("[slack image name=diagram.png")
    expect(parsed?.media[0]?.kind).toBe("image")
  })

  it("describes telegram photo messages", () => {
    const parsed = describeTelegramMedia({
      photo: [{ file_id: "small" }, { file_id: "large-id", file_size: 2048 }],
      caption: "screenshot",
    })
    expect(parsed?.content).toBe("screenshot")
    expect(parsed?.media[0]?.fileId).toBe("large-id")
  })

  it("downloads telegram files when caching enabled", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("getFile")) {
        return Response.json({ ok: true, result: { file_path: "photos/file.jpg", file_size: 10 } })
      }
      return new Response(Buffer.from("hello-media"), { status: 200 })
    })
    const result = await downloadTelegramFile({
      token: "tg-token",
      fileId: "abc",
      cacheDir: "/tmp/butler-v5-telegram-media-test",
      maxBytes: 1024,
      suggestedName: "photo.jpg",
      fetch: fetchMock as typeof fetch,
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.path).toContain("abc-photo.jpg")
    }
  })

  it("enriches inbound content with saved path", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("getFile")) {
        return Response.json({ ok: true, result: { file_path: "doc/x.pdf", file_size: 4 } })
      }
      return new Response(Buffer.from("data"), { status: 200 })
    })
    const enriched = await enrichTelegramMediaContent(
      {
        content: "[telegram image file_id=f1]",
        media: [{ kind: "image", fileId: "f1", mimeType: "image/jpeg" }],
      },
      {
        token: "tg-token",
        cacheDir: "/tmp/butler-v5-telegram-enrich-test",
        maxBytes: 1024,
        fetch: fetchMock as typeof fetch,
      },
    )
    expect(enriched.content).toContain("saved to")
  })
})
