import { describe, expect, it, vi } from "vitest"
import { mkdtemp, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { tmpdir } from "node:os"
import {
  isAllowedOutboundMediaPath,
  parseChannelOutboundMedia,
  resolveOutboundAttachment,
  sendTelegramOutboundMedia,
} from "./channel-outbound-media.js"
import { deliverTelegramChannelReply } from "./channel-outbound.js"

describe("channel outbound media", () => {
  it("parses [[media:path]] tags from reply", () => {
    const parsed = parseChannelOutboundMedia("Here is the chart.\n[[media:/tmp/chart.png]]")
    expect(parsed.text).toBe("Here is the chart.")
    expect(parsed.attachments).toEqual([
      { path: "/tmp/chart.png", kind: "image", name: "chart.png" },
    ])
  })

  it("allows media under workspace roots only", () => {
    const cwd = process.cwd()
    expect(isAllowedOutboundMediaPath(join(cwd, "foo.png"))).toBe(true)
    expect(isAllowedOutboundMediaPath("/etc/passwd")).toBe(false)
  })

  it("uploads telegram photo when outbound media enabled", async () => {
    const dir = await mkdtemp(join(tmpdir(), "butler-out-"))
    const filePath = join(dir, "shot.png")
    await writeFile(filePath, Buffer.from("png-bytes"))
    const fetchMock = vi.fn(async () => Response.json({ ok: true, result: {} }))
    const result = await deliverTelegramChannelReply({
      token: "tg-token",
      chatId: "99",
      reply: `see [[media:${filePath}]]`,
      env: { BUTLER_V5_CHANNEL_OUTBOUND_MEDIA: "1", BUTLER_V5_WORKSPACE: dir },
      fetch: fetchMock as typeof fetch,
    })
    expect(result.delivered).toBe(true)
    expect(result.mediaCount).toBe(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/sendPhoto")
  })

  it("reads attachment bytes from allowed path", async () => {
    const dir = await mkdtemp(join(tmpdir(), "butler-out-"))
    const filePath = join(dir, "doc.txt")
    await writeFile(filePath, "hello")
    const resolved = await resolveOutboundAttachment(
      { path: filePath, kind: "file", name: "doc.txt" },
      { BUTLER_V5_WORKSPACE: dir },
    )
    expect(resolved.ok).toBe(true)
    if (resolved.ok) expect(resolved.bytes.toString("utf8")).toBe("hello")
  })

  it("posts telegram sendDocument for non-image files", async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, result: {} }))
    const result = await sendTelegramOutboundMedia({
      token: "tg-token",
      chatId: "1",
      attachment: { path: "/x/report.pdf", kind: "file", name: "report.pdf" },
      bytes: Buffer.from("pdf"),
      fetch: fetchMock as typeof fetch,
    })
    expect(result).toEqual({ ok: true })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/sendDocument")
  })
})
