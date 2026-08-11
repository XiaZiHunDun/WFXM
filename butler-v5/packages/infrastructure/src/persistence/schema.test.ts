import { describe, it, expect } from "vitest"
import { events, outbox, intentReceipts, loadBearingMarks } from "./schema.js"

describe("persistence/schema", () => {
  describe("events table", () => {
    it("has expected columns", () => {
      const cols = Object.keys(events)
      expect(cols).toContain("id")
      expect(cols).toContain("streamId")
      expect(cols).toContain("version")
      expect(cols).toContain("type")
      expect(cols).toContain("payload")
      expect(cols).toContain("createdAt")
    })
  })

  describe("outbox table", () => {
    it("has expected columns", () => {
      const cols = Object.keys(outbox)
      expect(cols).toContain("id")
      expect(cols).toContain("aggregateId")
      expect(cols).toContain("type")
      expect(cols).toContain("payload")
      expect(cols).toContain("publishedAt")
      expect(cols).toContain("createdAt")
    })
  })

  describe("intentReceipts table", () => {
    it("has expected columns", () => {
      const cols = Object.keys(intentReceipts)
      expect(cols).toContain("id")
      expect(cols).toContain("intent")
      expect(cols).toContain("evidenceFiles")
      expect(cols).toContain("locDelta")
      expect(cols).toContain("chainCompleteness")
      expect(cols).toContain("guardFindings")
      expect(cols).toContain("authorAgent")
      expect(cols).toContain("reviewerAgent")
      expect(cols).toContain("ownerApprovalSig")
      expect(cols).toContain("createdAt")
    })
  })

  describe("loadBearingMarks table", () => {
    it("has expected columns", () => {
      const cols = Object.keys(loadBearingMarks)
      expect(cols).toContain("path")
      expect(cols).toContain("reason")
      expect(cols).toContain("markedBy")
      expect(cols).toContain("ownerApproved")
      expect(cols).toContain("alternatives")
      expect(cols).toContain("createdAt")
      expect(cols).toContain("updatedAt")
    })
  })
})
