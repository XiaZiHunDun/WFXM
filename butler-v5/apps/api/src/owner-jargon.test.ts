import { describe, expect, it } from "vitest"
import {
  describeEnvKnob,
  formatDecision,
  formatRunRef,
  publicPath,
  resolveProjectLabel,
} from "./owner-jargon.js"

describe("owner-jargon helpers", () => {
  describe("resolveProjectLabel", () => {
    it("returns the catalog label when present", () => {
      const env = {
        BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM,bot:Bot 频道",
      } as NodeJS.ProcessEnv
      expect(resolveProjectLabel("wechat", env)).toBe("WFXM")
      expect(resolveProjectLabel("bot", env)).toBe("Bot 频道")
    })

    it("falls back to raw id when catalog has no entry (preserves info)", () => {
      const env = {
        BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "wechat:WFXM",
      } as NodeJS.ProcessEnv
      expect(resolveProjectLabel("UNKNOWN", env)).toBe("UNKNOWN")
    })

    it("falls back to raw id when catalog is missing/malformed", () => {
      expect(resolveProjectLabel("WFXM", {} as NodeJS.ProcessEnv)).toBe("WFXM")
      expect(
        resolveProjectLabel("WFXM", {
          BUTLER_V5_PROJECT_KNOWLEDGE_INBOUND_MAP: "",
        } as NodeJS.ProcessEnv),
      ).toBe("WFXM")
    })
  })

  describe("formatRunRef", () => {
    it("strips run- prefix and truncates to 8 hex chars", () => {
      expect(formatRunRef("run-d2abc4567890")).toBe("运行 #d2abc456")
    })

    it("handles already-prefixed short ids", () => {
      expect(formatRunRef("run-abc")).toBe("运行 #abc")
    })

    it("handles non-run-prefixed ids", () => {
      expect(formatRunRef("d2abc4567890")).toBe("运行 #d2abc456")
    })
  })

  describe("formatDecision", () => {
    it("maps known decision enums to Chinese", () => {
      expect(formatDecision("Finish")).toBe("完成")
      expect(formatDecision("Respond")).toBe("已回复")
      expect(formatDecision("WaitForApproval")).toBe("等待审批")
      expect(formatDecision("WaitForTool")).toBe("等待工具执行")
      expect(formatDecision("MaxIterationsReached")).toBe("已达最大迭代次数")
    })

    it("passes through unknown values verbatim (operator can spot anomalies)", () => {
      expect(formatDecision("CustomFutureValue")).toBe("CustomFutureValue")
    })
  })

  describe("describeEnvKnob", () => {
    it("translates known BUTLER_V5_* knobs", () => {
      expect(describeEnvKnob("BUTLER_V5_CANDIDATE_EXPIRES_TTL_MS")).toBe(
        "候选过期时长",
      )
      expect(describeEnvKnob("BUTLER_V5_SCHEDULE_ENABLED")).toBe("定时任务开关")
    })

    it("falls back to '配置项 <name>' for unknown knobs", () => {
      expect(describeEnvKnob("BUTLER_V5_FUTURE_KNOB")).toBe("配置项 FUTURE_KNOB")
      expect(describeEnvKnob("UNKNOWN_PREFIX")).toBe("配置项 UNKNOWN_PREFIX")
    })
  })

  describe("publicPath", () => {
    it("strips workspace root prefix", () => {
      expect(publicPath("/workspace/foo/bar.ts", "/workspace")).toBe("foo/bar.ts")
    })

    it("returns absolute path when not under workspace root", () => {
      expect(publicPath("/other/foo.ts", "/workspace")).toBe("/other/foo.ts")
    })

    it("handles empty workspace root (returns absolute path verbatim)", () => {
      expect(publicPath("/workspace/foo.ts", "")).toBe("/workspace/foo.ts")
    })

    it("does not strip prefix that is only a substring (avoids /workspace2 → workspace)", () => {
      expect(publicPath("/workspace2/foo.ts", "/workspace")).toBe("/workspace2/foo.ts")
    })
  })
})
