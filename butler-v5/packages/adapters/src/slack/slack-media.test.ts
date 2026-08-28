import { describe, expect, it } from "vitest"
import { describeSlackFiles } from "./slack-media.js"

describe("describeSlackFiles", () => {
  it("returns null for empty array", () => {
    expect(describeSlackFiles([])).toBeNull()
  })

  it("returns null for null input", () => {
    expect(describeSlackFiles(null)).toBeNull()
  })

  it("returns null for undefined input", () => {
    expect(describeSlackFiles(undefined)).toBeNull()
  })

  it("returns null for non-array input", () => {
    expect(describeSlackFiles("not array")).toBeNull()
    expect(describeSlackFiles({})).toBeNull()
  })

  it("returns null when all entries are skipped", () => {
    expect(describeSlackFiles([null, 42, "string"])).toBeNull()
  })

  it("describes a single image file with caption", () => {
    const parsed = describeSlackFiles(
      [{ name: "diagram.png", mimetype: "image/png", size: 1024 }],
      "see this",
    )
    expect(parsed?.content).toContain("see this")
    expect(parsed?.content).toContain("[slack image name=diagram.png mimetype=image/png]")
    expect(parsed?.media[0]?.kind).toBe("image")
    expect(parsed?.media[0]?.name).toBe("diagram.png")
    expect(parsed?.media[0]?.sizeBytes).toBe(1024)
  })

  it("describes a single image file without caption", () => {
    const parsed = describeSlackFiles([{ name: "a.png", mimetype: "image/png", size: 100 }])
    expect(parsed?.content).toBe("[slack image name=a.png mimetype=image/png]")
    expect(parsed?.media).toHaveLength(1)
  })

  it("falls back to 'attachment' name when file has no name", () => {
    const parsed = describeSlackFiles([{ mimetype: "image/png", size: 100 }])
    expect(parsed?.content).toContain("name=attachment")
    expect(parsed?.media[0]?.name).toBe("attachment")
  })

  it("falls back to octet-stream mimetype when missing", () => {
    const parsed = describeSlackFiles([{ name: "a.bin", size: 100 }])
    expect(parsed?.content).toContain("mimetype=application/octet-stream")
    expect(parsed?.media[0]?.mimeType).toBe("application/octet-stream")
  })

  it("classifies audio mimetype as audio kind", () => {
    const parsed = describeSlackFiles([{ name: "voice.mp3", mimetype: "audio/mpeg", size: 5000 }])
    expect(parsed?.media[0]?.kind).toBe("audio")
    expect(parsed?.content).toContain("[slack audio")
  })

  it("classifies video mimetype as video kind", () => {
    const parsed = describeSlackFiles([{ name: "movie.mp4", mimetype: "video/mp4", size: 1_000_000 }])
    expect(parsed?.media[0]?.kind).toBe("video")
    expect(parsed?.content).toContain("[slack video")
  })

  it("classifies unknown mimetype as file kind", () => {
    const parsed = describeSlackFiles([{ name: "doc.pdf", mimetype: "application/pdf", size: 200 }])
    expect(parsed?.media[0]?.kind).toBe("file")
  })

  it("skips non-object entries but processes valid ones", () => {
    const parsed = describeSlackFiles([
      null,
      { name: "a.png", mimetype: "image/png", size: 100 },
      42,
      "string",
      { name: "b.pdf", mimetype: "application/pdf", size: 50 },
    ])
    expect(parsed?.media).toHaveLength(2)
    expect(parsed?.media[0]?.name).toBe("a.png")
    expect(parsed?.media[1]?.name).toBe("b.pdf")
  })

  it("captures url_private when present", () => {
    const parsed = describeSlackFiles([
      { name: "x.png", mimetype: "image/png", size: 100, url_private: "https://files.slack.com/x" },
    ])
    expect(parsed?.media[0]?.url).toBe("https://files.slack.com/x")
  })

  it("omits url when url_private missing", () => {
    const parsed = describeSlackFiles([{ name: "x.png", mimetype: "image/png", size: 100 }])
    expect(parsed?.media[0]?.url).toBeUndefined()
  })

  it("omits sizeBytes when size missing", () => {
    const parsed = describeSlackFiles([{ name: "x.png", mimetype: "image/png" }])
    expect(parsed?.media[0]?.sizeBytes).toBeUndefined()
  })

  it("ignores non-number size", () => {
    const parsed = describeSlackFiles([{ name: "x.png", mimetype: "image/png", size: "huge" }])
    expect(parsed?.media[0]?.sizeBytes).toBeUndefined()
  })

  it("trims file name whitespace", () => {
    const parsed = describeSlackFiles([{ name: "  spaced.png  ", mimetype: "image/png", size: 10 }])
    expect(parsed?.media[0]?.name).toBe("spaced.png")
  })

  it("treats empty file name as attachment", () => {
    const parsed = describeSlackFiles([{ name: "   ", mimetype: "image/png", size: 10 }])
    expect(parsed?.media[0]?.name).toBe("attachment")
  })

  it("formats multi-file caption correctly", () => {
    const parsed = describeSlackFiles(
      [
        { name: "a.png", mimetype: "image/png", size: 100 },
        { name: "b.pdf", mimetype: "application/pdf", size: 200 },
      ],
      "two files",
    )
    expect(parsed?.content).toContain("two files")
    expect(parsed?.content).toContain("[slack image name=a.png")
    expect(parsed?.content).toContain("[slack file name=b.pdf")
    expect(parsed?.content.split("\n")).toHaveLength(3) // caption + 2 lines
  })
})