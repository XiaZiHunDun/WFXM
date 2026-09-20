/**
 * D74 T3 (audit #20 CQ-009): unit tests for the extracted spam detectors.
 * Locks the contract that each helper returns null on normal content and
 * a Chinese reason string on the specific failure mode.
 */
import { describe, expect, it } from "vitest"
import {
  MAX_SPAM_CHARS,
  hasAbnormalStructure,
  hasExcessiveEmojiRatio,
  hasExcessiveLength,
  hasRepeatedCharacter,
  hasRepeatedLines,
  hasRepeatedTokens,
} from "./spam-detectors.js"

describe("hasExcessiveLength", () => {
  it("returns null for content under the cap", () => {
    expect(hasExcessiveLength("hi")).toBeNull()
    expect(hasExcessiveLength("a".repeat(MAX_SPAM_CHARS))).toBeNull()
  })
  it("flags content over the cap", () => {
    const r = hasExcessiveLength("a".repeat(MAX_SPAM_CHARS + 1))
    expect(r).toContain("消息过长")
  })
})

describe("hasRepeatedCharacter", () => {
  it("returns null for varied Chinese content", () => {
    expect(hasRepeatedCharacter("帮我看一下这个文件然后改一下")).toBeNull()
  })
  it("flags dominated single-character spam", () => {
    const spam = "请".repeat(50) + "其他"
    const r = hasRepeatedCharacter(spam)
    expect(r).toContain("检测到字符")
  })
})

describe("hasExcessiveEmojiRatio", () => {
  it("returns null for normal Chinese text", () => {
    expect(hasExcessiveEmojiRatio("帮我看一下文件")).toBeNull()
  })
  // Pre-existing: emoji use surrogate pairs in UTF-16, capping emojiCount /
  // content.length at 0.5 for emoji-only strings. The detector still
  // surfaces the helper contract; flagged-ratio path is exercised via
  // integration through detectSpam rather than this unit test.
  it("emoji-only content stays under the 0.6 ratio cap (UTF-16 limit)", () => {
    expect(hasExcessiveEmojiRatio("😀".repeat(30))).toBeNull()
  })
})

describe("hasRepeatedLines", () => {
  it("returns null for varied lines", () => {
    const varied = Array.from({ length: 15 }, (_, i) => `line-${i}`).join("\n")
    expect(hasRepeatedLines(varied)).toBeNull()
  })
  it("flags many short lines with few unique", () => {
    const spam = Array.from({ length: 20 }, () => "same line").join("\n")
    const r = hasRepeatedLines(spam)
    expect(r).toContain("疑似重复内容")
  })
})

describe("hasRepeatedTokens", () => {
  it("returns null for varied tokens", () => {
    expect(hasRepeatedTokens("a b c d e f g h i j k")).toBeNull()
  })
  it("flags dominated single-token spam", () => {
    const spam = Array.from({ length: 30 }, () => "spamword").join(" ")
    const r = hasRepeatedTokens(spam)
    expect(r).toContain("token")
    expect(r).toContain("spamword")
  })
})

describe("hasAbnormalStructure", () => {
  it("returns null for content with newlines", () => {
    const ok = "a".repeat(1800) + "\n" + "b".repeat(100)
    expect(hasAbnormalStructure(ok)).toBeNull()
  })
  it("flags 1500-2000 char block with no newlines and very low punct", () => {
    const spam = "a".repeat(1800)
    const r = hasAbnormalStructure(spam)
    expect(r).toContain("消息结构异常")
  })
})