import { describe, expect, it } from "vitest"
import {
  ALLOWED_SUBJECTS,
  describeEnvKnob,
  formatDecision,
  formatRunRef,
  isAllowedSubject,
  mapChannelErrorToOwnerJargon,
  resolveProjectLabel,
  safeOwnerErrorString,
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

  // D74 T1 (audit #20 SO-006): domain English → owner Chinese.
  describe("safeOwnerErrorString", () => {
    it("maps known domain validator reasons to Chinese", () => {
      expect(safeOwnerErrorString("projectId is required")).toBe("缺少 projectId 参数")
      expect(safeOwnerErrorString("projectId is required for project knowledge recall")).toBe("缺少 projectId 参数")
      expect(safeOwnerErrorString("subject is required")).toBe("缺少 subject 参数")
      expect(safeOwnerErrorString("content exceeds 4000 chars")).toBe("内容超出长度限制（最多 4000 字）")
      expect(safeOwnerErrorString("name is required")).toBe("缺少名称参数")
      expect(safeOwnerErrorString("unsupported format")).toBe("不支持的文档格式")
    })

    it("maps PG error substrings (SO-003) to Chinese", () => {
      expect(
        safeOwnerErrorString('invalid input syntax for type uuid: "missing-id"'),
      ).toBe("未找到对应记录")
      expect(
        safeOwnerErrorString(
          'duplicate key value violates unique constraint "memories_pkey"',
        ),
      ).toBe("与已有记录重复")
    })

    it("uses generic fallback for unknown reasons", () => {
      expect(safeOwnerErrorString("totally unknown reason")).toBe(
        "操作失败，请稍后重试",
      )
      expect(safeOwnerErrorString("unknown", "自定义兜底")).toBe("自定义兜底")
    })

    it("handles non-string input defensively", () => {
      // @ts-expect-error -- exercising runtime defensive narrowing
      expect(safeOwnerErrorString(undefined)).toBe("操作失败，请稍后重试")
      // @ts-expect-error -- exercising runtime defensive narrowing
      expect(safeOwnerErrorString(null, "兜底")).toBe("兜底")
    })
  })

  // D74 T1 (audit #20 SO-007): subject allowlist for audit emit.
  describe("isAllowedSubject / ALLOWED_SUBJECTS", () => {
    it("accepts the documented sentinel values", () => {
      expect(isAllowedSubject("owner")).toBe(true)
      expect(isAllowedSubject("assistant")).toBe(true)
      expect(isAllowedSubject("system")).toBe(true)
    })

    it("rejects attacker-controlled strings", () => {
      expect(isAllowedSubject("other-user")).toBe(false)
      expect(isAllowedSubject("admin")).toBe(false)
      expect(isAllowedSubject("")).toBe(false)
      expect(isAllowedSubject("OWNER")).toBe(false) // case-sensitive
    })

    it("rejects non-string input defensively", () => {
      expect(isAllowedSubject(undefined)).toBe(false)
      expect(isAllowedSubject(null)).toBe(false)
      expect(isAllowedSubject(42)).toBe(false)
    })

    it("exports the allowlist as a frozen ReadonlySet", () => {
      expect(ALLOWED_SUBJECTS.size).toBe(3)
      expect(ALLOWED_SUBJECTS.has("owner")).toBe(true)
    })
  })

  // D74 T1 (audit #20 SO-002 + SO-029): Telegram API error → owner Chinese.
  describe("mapChannelErrorToOwnerJargon", () => {
    it("maps our own English fallback templates to Chinese", () => {
      expect(mapChannelErrorToOwnerJargon("telegram API HTTP 500")).toBe(
        "Telegram 接口返回错误（状态 500）",
      )
      expect(mapChannelErrorToOwnerJargon("telegram API timeout after 15000ms")).toBe(
        "Telegram 接口响应超时（15000 毫秒）",
      )
    })

    it("maps upstream Telegram API descriptions to Chinese", () => {
      expect(mapChannelErrorToOwnerJargon("Bad Request: chat not found")).toBe(
        "对话不存在或无法访问",
      )
      expect(mapChannelErrorToOwnerJargon("Forbidden: bot was blocked by the user")).toBe(
        "用户已屏蔽此机器人",
      )
      expect(mapChannelErrorToOwnerJargon("Too Many Requests: retry after 30")).toBe(
        "调用频率过高，请稍后重试",
      )
    })

    it("falls back to safeOwnerErrorString → generic for unknown shapes", () => {
      expect(mapChannelErrorToOwnerJargon("completely unrecognised upstream blurb")).toBe(
        "Telegram 接口调用失败",
      )
    })

    it("handles non-string input defensively", () => {
      // @ts-expect-error -- exercising runtime defensive narrowing
      expect(mapChannelErrorToOwnerJargon(undefined)).toBe("Telegram 接口调用失败")
    })
  })
})
