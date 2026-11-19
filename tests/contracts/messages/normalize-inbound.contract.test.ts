// 锚定：入站消息规范化契约（normalizeWechatInbound / normalizeChannelInbound）
// —— 只断言对外可见的 NormalizedInbound 字段、错误 kind、turnId/幂等键形态。
// 不断言内部实现路径、不比对错误 reason 文案、不依赖 DB/网络。
import { describe, expect, it } from "vitest"
import {
  normalizeChannelInbound,
  normalizeWechatInbound,
  type NormalizedInbound,
  type NormalizeInboundResult,
} from "../../../packages/runtime/src/intake/normalize-inbound.js"
import { validateRunTrigger } from "../../../packages/domain/src/runtime/index.js"
import {
  CONTROL_CHARS,
  CONVERSATION_ID_MAX_LEN,
  FIXED_NOW_MS,
  LONG_TEXT_200K,
  MIXED_TEXT,
  VALID_CONVERSATION_ID,
} from "./messages-fixtures.js"

interface CaseInput {
  readonly content: unknown
  readonly identity?: string
  readonly channelId?: string
  readonly projectId?: string
  readonly conversationId?: unknown
  readonly messageId?: string
  readonly nowMs?: number
}

interface NormalizeEntry {
  readonly name: string
  readonly keyPrefix: "wechat" | "channel"
  readonly expectedProjectId: string
  readonly defaultConversationId: string
  readonly normalize: (input: CaseInput) => NormalizeInboundResult
}

/** 两条入口用同一份输入表驱动；入口差异（字段名/默认 id）收敛在适配器里。 */
const ENTRIES: readonly NormalizeEntry[] = [
  {
    name: "wechat 入站",
    keyPrefix: "wechat",
    expectedProjectId: "wechat",
    defaultConversationId: "c-wechat-u-1",
    normalize: (input) =>
      normalizeWechatInbound({
        fromUserId: input.identity ?? "u-1",
        content: input.content as string,
        ...(input.messageId === undefined ? {} : { messageId: input.messageId }),
        ...(input.projectId === undefined ? {} : { projectId: input.projectId }),
        ...(input.conversationId === undefined ? {} : { conversationId: input.conversationId }),
        ...(input.nowMs === undefined ? {} : { nowMs: input.nowMs }),
      }),
  },
  {
    name: "channel 入站",
    keyPrefix: "channel",
    expectedProjectId: "channel:slack",
    defaultConversationId: "c-ch-slack-u-1",
    normalize: (input) =>
      normalizeChannelInbound({
        channelId: input.channelId ?? "slack",
        fromSubject: input.identity ?? "u-1",
        content: input.content as string,
        ...(input.messageId === undefined ? {} : { messageId: input.messageId }),
        ...(input.conversationId === undefined ? {} : { conversationId: input.conversationId }),
        ...(input.nowMs === undefined ? {} : { nowMs: input.nowMs }),
      }),
  },
]

function expectOk(result: NormalizeInboundResult): NormalizedInbound {
  expect(result.ok, "应规范化成功").toBe(true)
  if (!result.ok) throw new Error(`expected ok, got ${result.error.kind}`)
  return result.value
}

function expectError(
  result: NormalizeInboundResult,
  kind: "invalid_body" | "invalid_conversation_id",
): void {
  expect(result.ok, "应返回错误而不是抛出异常").toBe(false)
  if (result.ok) throw new Error("expected failure")
  expect(result.error.kind).toBe(kind)
  // 只要求 reason 是给调用方可读的非空字符串，不比对具体文案。
  expect(result.error.reason.trim().length).toBeGreaterThan(0)
}

const ACCEPTED_SHAPES = [
  { name: "纯文本", content: "你好，帮我看下登录超时" },
  { name: "空字符串", content: "" },
  { name: "超长文本（200k 字符）", content: LONG_TEXT_200K },
  { name: "emoji + 中英混合", content: MIXED_TEXT },
  { name: "控制字符（NUL/BEL/ANSI/DEL）", content: CONTROL_CHARS },
] as const

describe.each(ENTRIES)("$name：数据形态矩阵", (entry) => {
  for (const shape of ACCEPTED_SHAPES) {
    it(`接受「${shape.name}」并原样保留 content`, () => {
      const value = expectOk(entry.normalize({ content: shape.content, nowMs: FIXED_NOW_MS }))
      // 规范化层不做截断/清洗：内容形态由下游（spam guard / 渲染）处理。
      expect(value.content).toBe(shape.content)
      expect(value.source).toBe(entry.keyPrefix)
      expect(value.subject).toBe("u-1")
      expect(value.projectId).toBe(entry.expectedProjectId)
      expect(value.conversationId).toBe(entry.defaultConversationId)
      expect(value.turnId).toBe(`turn-${FIXED_NOW_MS}`)
      expect(value.messageId).toBeUndefined()
      expect(value.idempotencyKey).toBe(
        `${entry.keyPrefix}-${entry.defaultConversationId}-turn-${FIXED_NOW_MS}`,
      )
      expect(value.conversationId).toMatch(/^[A-Za-z0-9_.:-]+$/)
      expect(value.conversationId.length).toBeLessThanOrEqual(CONVERSATION_ID_MAX_LEN)
    })
  }

  const INVALID_CONTENT = [
    { name: "number", content: 42 },
    { name: "null", content: null },
    { name: "undefined", content: undefined },
    { name: "object", content: { text: "hi" } },
  ] as const

  for (const bad of INVALID_CONTENT) {
    it(`content 类型为 ${bad.name} → invalid_body`, () => {
      expectError(entry.normalize({ content: bad.content }), "invalid_body")
    })
  }

  for (const identity of ["", "   ", "\n\t"]) {
    it(`身份为空白（${JSON.stringify(identity)}）→ invalid_body`, () => {
      expectError(entry.normalize({ content: "hi", identity }), "invalid_body")
    })
  }

  it("身份两侧空白被 trim，并进入 subject 与默认会话 id", () => {
    const value = expectOk(
      entry.normalize({ content: "hi", identity: "  u-9  ", nowMs: FIXED_NOW_MS }),
    )
    expect(value.subject).toBe("u-9")
    expect(value.conversationId).toBe(
      entry.keyPrefix === "wechat" ? "c-wechat-u-9" : "c-ch-slack-u-9",
    )
  })
})

describe("channel 入口：channelId 契约", () => {
  it("空白 channelId → invalid_body", () => {
    expectError(
      normalizeChannelInbound({
        channelId: "   ",
        fromSubject: "s-1",
        content: "hi",
      }),
      "invalid_body",
    )
  })

  it("channelId 两侧空白被 trim，并反映在 projectId / 默认会话 id", () => {
    const value = expectOk(
      normalizeChannelInbound({
        channelId: "  slack  ",
        fromSubject: "U1",
        content: "hi",
        nowMs: FIXED_NOW_MS,
      }),
    )
    expect(value.projectId).toBe("channel:slack")
    expect(value.conversationId).toBe("c-ch-slack-U1")
  })
})

describe("wechat 入口：projectId 契约", () => {
  it("projectId 经过 trim 与 id 清洗后进入默认会话 id", () => {
    const value = expectOk(
      normalizeWechatInbound({
        fromUserId: "u-1",
        content: "hi",
        projectId: "  proj A  ",
        nowMs: FIXED_NOW_MS,
      }),
    )
    expect(value.projectId).toBe("proj A")
    expect(value.conversationId).toBe("c-proj-A-u-1")
  })
})

describe.each(ENTRIES)("$name：conversationId 契约", (entry) => {
  const VALID_CASES = [
    { name: "合法自定义 id", raw: VALID_CONVERSATION_ID, expected: VALID_CONVERSATION_ID },
    {
      name: "两侧空白被 trim",
      raw: `  ${VALID_CONVERSATION_ID}  `,
      expected: VALID_CONVERSATION_ID,
    },
    {
      name: "长度等于上限",
      raw: "x".repeat(CONVERSATION_ID_MAX_LEN),
      expected: "x".repeat(CONVERSATION_ID_MAX_LEN),
    },
  ] as const

  for (const valid of VALID_CASES) {
    it(`接受自定义会话 id：${valid.name}`, () => {
      const value = expectOk(
        entry.normalize({ content: "hi", conversationId: valid.raw, nowMs: FIXED_NOW_MS }),
      )
      expect(value.conversationId).toBe(valid.expected)
      expect(value.idempotencyKey).toBe(`${entry.keyPrefix}-${valid.expected}-turn-${FIXED_NOW_MS}`)
    })
  }

  const INVALID_CASES = [
    { name: "空字符串", raw: "" },
    { name: "纯空白", raw: "   " },
    { name: "含斜杠", raw: "bad/id" },
    { name: "含空格", raw: "c 1" },
    { name: "含中文", raw: "会话-1" },
    { name: "含 emoji", raw: "c-🚀" },
    { name: "超过长度上限", raw: "x".repeat(CONVERSATION_ID_MAX_LEN + 1) },
    { name: "number 类型", raw: 123 },
    { name: "object 类型", raw: {} },
  ] as const

  for (const invalid of INVALID_CASES) {
    it(`拒绝非法会话 id：${invalid.name} → invalid_conversation_id`, () => {
      expectError(
        entry.normalize({ content: "hi", conversationId: invalid.raw }),
        "invalid_conversation_id",
      )
    })
  }

  it("conversationId 为 null/缺省时回落到默认会话 id", () => {
    const withNull = expectOk(
      entry.normalize({ content: "hi", conversationId: null, nowMs: FIXED_NOW_MS }),
    )
    const absent = expectOk(entry.normalize({ content: "hi", nowMs: FIXED_NOW_MS }))
    expect(withNull.conversationId).toBe(entry.defaultConversationId)
    expect(absent.conversationId).toBe(entry.defaultConversationId)
  })
})

describe.each(ENTRIES)("$name：messageId / 幂等键规则", (entry) => {
  const generatedKey = (conversationId: string, nowMs: number): string =>
    `${entry.keyPrefix}-${conversationId}-turn-${nowMs}`

  it("缺省 messageId：由「前缀 + 会话 + turn」生成确定性幂等键", () => {
    const value = expectOk(entry.normalize({ content: "hi", nowMs: FIXED_NOW_MS }))
    expect(value.messageId).toBeUndefined()
    expect(value.idempotencyKey).toBe(generatedKey(entry.defaultConversationId, FIXED_NOW_MS))
  })

  it("messageId 两侧空白被 trim 后作为幂等键复用", () => {
    const value = expectOk(
      entry.normalize({ content: "hi", messageId: "  msg-1  ", nowMs: FIXED_NOW_MS }),
    )
    expect(value.messageId).toBe("msg-1")
    expect(value.idempotencyKey).toBe("msg-1")
  })

  it("纯空白 messageId 视为缺省（回落到生成键）", () => {
    const value = expectOk(
      entry.normalize({ content: "hi", messageId: "   ", nowMs: FIXED_NOW_MS }),
    )
    expect(value.messageId).toBeUndefined()
    expect(value.idempotencyKey).toBe(generatedKey(entry.defaultConversationId, FIXED_NOW_MS))
  })

  // 投递壳（apps/api）的 replayDuplicateInbound 以「会话内 user 消息的该键」
  // 判定重投并回放已存回复；此处只锚定键本身，不触碰 DB/内部路径。
  it("同一 messageId 在不同 nowMs 下复用同一幂等键（重投不重复执行）", () => {
    const first = expectOk(entry.normalize({ content: "hi", messageId: "dup-1", nowMs: 1 }))
    const second = expectOk(entry.normalize({ content: "hi", messageId: "dup-1", nowMs: 2 }))
    expect(first.idempotencyKey).toBe(second.idempotencyKey)
    // turnId 仍然随到达时间前进，但幂等键不随之变化。
    expect(first.turnId).not.toBe(second.turnId)
  })

  it("缺省 messageId 时不同 nowMs 产生不同幂等键", () => {
    const first = expectOk(entry.normalize({ content: "hi", nowMs: 1 }))
    const second = expectOk(entry.normalize({ content: "hi", nowMs: 2 }))
    expect(first.idempotencyKey).not.toBe(second.idempotencyKey)
  })

  it("缺省 messageId 时不同会话产生不同幂等键", () => {
    const first = expectOk(
      entry.normalize({ content: "hi", conversationId: "c-a", nowMs: FIXED_NOW_MS }),
    )
    const second = expectOk(
      entry.normalize({ content: "hi", conversationId: "c-b", nowMs: FIXED_NOW_MS }),
    )
    expect(first.idempotencyKey).not.toBe(second.idempotencyKey)
  })

  it("同一 messageId 跨会话保持同键（去重必须按会话作用域）", () => {
    const first = expectOk(
      entry.normalize({ content: "hi", conversationId: "c-a", messageId: "m-1", nowMs: 1 }),
    )
    const second = expectOk(
      entry.normalize({ content: "hi", conversationId: "c-b", messageId: "m-1", nowMs: 2 }),
    )
    expect(first.idempotencyKey).toBe("m-1")
    expect(second.idempotencyKey).toBe("m-1")
  })

  it("RunTrigger 携带同一主体/会话/幂等键，且通过领域校验", () => {
    const value = expectOk(
      entry.normalize({
        content: "hi",
        conversationId: VALID_CONVERSATION_ID,
        messageId: "m-1",
        nowMs: FIXED_NOW_MS,
      }),
    )
    expect(value.runTrigger.subject).toBe(value.subject)
    expect(value.runTrigger.conversationRef).toBe(value.conversationId)
    expect(value.runTrigger.idempotencyKey).toBe(value.idempotencyKey)
    expect(value.runTrigger.source).toBe(entry.keyPrefix === "wechat" ? "channel" : "webhook")
    expect(validateRunTrigger(value.runTrigger)).toEqual({ ok: true })
  })
})
