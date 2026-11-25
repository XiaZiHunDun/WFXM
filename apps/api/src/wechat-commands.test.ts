// Anchors: wechat command semantics (routing, reply intent, persisted state).
// Merged from the former per-command files; one shared harness, no per-command
// boilerplate. Prompts/internals are not asserted.
import { beforeEach, afterEach, describe, expect, it } from "vitest"
import { createDurableMemoryStore, type DurableMemoryStore } from "@butler/persistence"
import { createDurableMemoryRecord } from "@butler/domain/knowledge/durable-memory.js"
import { setWechatActiveProjectId } from "./wechat-active-project.js"
import { tryWechatInboundCommand } from "./wechat-inbound-commands.js"
import { tryWechatMemoryCommand } from "./wechat-memory-commands.js"
import { tryWechatSubagentCommand } from "./wechat-subagent-commands.js"
import {
  makeWechatCommandHarness,
  type WechatCommandHarness,
} from "../../../tests/wechat-command-harness.js"

let h: WechatCommandHarness

beforeEach(async () => {
  h = await makeWechatCommandHarness("wechat-cmd")
})

afterEach(async () => {
  await h.close()
})

describe("wechat command routing", () => {
  it("creates and lists project-scoped tasks", async () => {
    const add = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-task",
      content: "/待办 新增 修 smoke",
      env: h.env,
    })
    expect(add?.reply).toContain("已添加待办")

    const list = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-task",
      content: "/待办",
      env: h.env,
    })
    expect(list?.reply).toContain("修 smoke")
  })

  it("remembers as a candidate, then promotes it via 确认记忆", async () => {
    const remember = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-mem",
      content: "/记住 第三卷主角名禁止修改",
      env: h.env,
    })
    expect(remember?.reply).toContain("已记录候选记忆")

    const pending = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-mem",
      content: "/记忆候选",
      env: h.env,
    })
    expect(pending?.reply).toContain("第三卷")

    const confirmed = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-mem",
      content: "/确认记忆",
      env: h.env,
    })
    expect(confirmed?.reply).toContain("已确认记忆")

    const list = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-mem",
      content: "/记忆",
      env: h.env,
    })
    expect(list?.reply).toContain("第三卷")
  })
})

describe("memory commands", () => {
  it("persists natural-language 记住：… instead of leaving it to the model", async () => {
    const result = await tryWechatMemoryCommand({
      wiring: h.wiring,
      fromUserId: "u-mem-natural",
      content: "记住：我下周要去成都出差",
      env: h.env,
    })
    expect(result?.reply).toContain("已记录候选记忆")
    const saved = await h.wiring.durableMemoryStore?.listBySubject({
      subject: "u-mem-natural",
      status: "candidate",
      limit: 10,
    })
    expect(saved?.some((item) => item.content.includes("成都"))).toBe(true)
  })

  it("records /纠错 as a candidate and audits memory.correction", async () => {
    const result = await tryWechatMemoryCommand({
      wiring: h.wiring,
      fromUserId: "u-mem-fix",
      content: "/纠错 主角名是林川，不是林晨",
      env: h.env,
    })
    expect(result?.reply).toContain("已记录纠错候选")
    expect(result?.traces[0]?.startsWith("wechat-memory: correction-candidate")).toBe(true)
    const candidates = await h.wiring.durableMemoryStore?.listBySubject({
      subject: "u-mem-fix",
      status: "candidate",
      limit: 10,
    })
    expect(candidates?.[0]?.content).toContain("林川")
    expect(candidates?.[0]?.provenance.note).toContain("correction")
    const audits = await h.wiring.runtimeStore.listRecentAuditEvents({
      windowMs: 60_000,
      limit: 20,
    })
    expect(audits.some((event) => event.action === "memory.correction")).toBe(true)
  })

  it("does not hijack questions like 你还记得吗", async () => {
    const result = await tryWechatMemoryCommand({
      wiring: h.wiring,
      fromUserId: "u-mem-natural",
      content: "你还记得吗",
      env: h.env,
    })
    expect(result).toBeNull()
  })

  it("surfaces dedup outage to the owner but still writes (fail-open)", async () => {
    const realStore = createDurableMemoryStore(h.db.db)
    const degradedStore: DurableMemoryStore = {
      ...realStore,
      findCandidatesForDedup: async () => {
        throw new Error("simulated dedup outage")
      },
    }
    const result = await tryWechatMemoryCommand({
      wiring: { ...h.wiring, durableMemoryStore: degradedStore },
      fromUserId: "u-mem",
      content: "/记住 测试内容 dedup 应该 fail-open 但 owner 要知道",
      env: h.env,
    })
    expect(result).not.toBeNull()
    if (result === null) return
    expect(result.reply).toContain("已记录候选记忆")
    expect(result.reply).toContain("去重检查失败")
    expect(result.reply).not.toContain("simulated dedup outage")
  })

  it("/记住 returns dedup message when a similar memory exists", async () => {
    const seed = createDurableMemoryRecord({
      subject: "owner-dedup-wechat",
      content: "第三卷主角名禁止修改",
      sourceKind: "owner",
      status: "confirmed",
    })
    if (!seed.ok) throw new Error("seed")
    const store = h.wiring.durableMemoryStore
    if (!store) throw new Error("test setup: durableMemoryStore required")
    await store.create(seed.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-dedup-wechat",
      content: "/记住 第三卷主角名禁止修改",
      env: h.env,
    })
    expect(result?.reply).toContain("相似度")
    expect(result?.reply).toContain("请先确认是否重复")
    expect(result?.reply).not.toContain("已记录候选记忆")
  })
})

describe("memory candidate review", () => {
  const store = () => {
    const s = h.wiring.durableMemoryStore
    if (!s) throw new Error("test setup: durableMemoryStore required")
    return s
  }

  it("/记忆候选 lists pending candidates scoped to the active project", async () => {
    setWechatActiveProjectId("owner-A", "WFXM", h.env)
    const records = [
      createDurableMemoryRecord({
        subject: "owner-A",
        content: "fact-in-active",
        sourceKind: "owner",
        status: "candidate",
        provenance: { note: "project:WFXM" },
      }),
      createDurableMemoryRecord({
        subject: "owner-A",
        content: "fact-un-noted",
        sourceKind: "owner",
        status: "candidate",
      }),
      createDurableMemoryRecord({
        subject: "owner-A",
        content: "fact-other-project",
        sourceKind: "owner",
        status: "candidate",
        provenance: { note: "project:OTHER" },
      }),
    ]
    for (const r of records) {
      if (!r.ok) throw new Error("seed")
      await store().create(r.value)
    }

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: "/记忆候选",
      env: h.env,
    })
    expect(result?.reply).toContain("候选")
    expect(result?.reply).toContain("fact-in-active")
    expect(result?.reply).toContain("fact-un-noted")
    expect(result?.reply).not.toContain("fact-other-project")
  })

  it("/记忆候选 returns empty message when no candidates", async () => {
    setWechatActiveProjectId("owner-no-candidates", "WFXM", h.env)
    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-no-candidates",
      content: "/记忆候选",
      env: h.env,
    })
    expect(result?.reply).toContain("暂无待审记忆")
  })

  it("/确认记忆 id1,id2 confirms both", async () => {
    const a = createDurableMemoryRecord({
      subject: "owner-A",
      content: "batch-A",
      sourceKind: "owner",
      status: "candidate",
    })
    const b = createDurableMemoryRecord({
      subject: "owner-A",
      content: "batch-B",
      sourceKind: "owner",
      status: "candidate",
    })
    if (!a.ok || !b.ok) throw new Error("seed")
    const s1 = await store().create(a.value)
    const s2 = await store().create(b.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: `/确认记忆 ${s1.id},${s2.id}`,
      env: h.env,
    })
    expect(result?.reply).toContain("已确认 2 条记忆")
    expect(result?.reply).not.toContain("失败")
    expect(result?.reply).not.toContain(s1.id.slice(0, 8))
  })

  it("/确认记忆 reports partial failure without leaking raw ids", async () => {
    const a = createDurableMemoryRecord({
      subject: "owner-A",
      content: "only",
      sourceKind: "owner",
      status: "candidate",
    })
    if (!a.ok) throw new Error("seed")
    const s1 = await store().create(a.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: `/确认记忆 ${s1.id},missing-id`,
      env: h.env,
    })
    expect(result?.reply).toContain("已确认 1 条记忆")
    expect(result?.reply).toContain("未确认")
    expect(result?.reply).not.toContain("missing-id")
    expect(result?.reply).not.toContain("not found")
  })

  it("/确认记忆 with no argument confirms the newest candidate", async () => {
    const a = createDurableMemoryRecord({
      subject: "owner-A",
      content: "regression-1",
      sourceKind: "owner",
      status: "candidate",
    })
    const b = createDurableMemoryRecord({
      subject: "owner-A",
      content: "regression-2",
      sourceKind: "owner",
      status: "candidate",
      nowMs: Date.now() + 1000,
    })
    if (!a.ok || !b.ok) throw new Error("seed")
    await store().create(a.value)
    const s2 = await store().create(b.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: "/确认记忆",
      env: h.env,
    })
    expect(result?.reply).toContain(`已确认记忆 ${s2.id.slice(0, 8)}`)
  })

  it("/确认记忆 accepts a single short token (legacy usage)", async () => {
    const a = createDurableMemoryRecord({
      subject: "owner-A",
      content: "single",
      sourceKind: "owner",
      status: "candidate",
    })
    if (!a.ok) throw new Error("seed")
    const s1 = await store().create(a.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: `/确认记忆 ${s1.id.slice(0, 8)}`,
      env: h.env,
    })
    expect(result?.reply).toContain(`已确认记忆 ${s1.id.slice(0, 8)}`)
  })

  it("/确认记忆 with only a comma falls back to the newest candidate", async () => {
    const a = createDurableMemoryRecord({
      subject: "owner-A",
      content: "only-comma-1",
      sourceKind: "owner",
      status: "candidate",
    })
    const b = createDurableMemoryRecord({
      subject: "owner-A",
      content: "only-comma-2",
      sourceKind: "owner",
      status: "candidate",
      nowMs: Date.now() + 1000,
    })
    if (!a.ok || !b.ok) throw new Error("seed")
    await store().create(a.value)
    const s2 = await store().create(b.value)

    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "owner-A",
      content: "/确认记忆 ,",
      env: h.env,
    })
    expect(result?.reply).toContain(`已确认记忆 ${s2.id.slice(0, 8)}`)
  })
})

describe("observability commands", () => {
  const ownerEnv: NodeJS.ProcessEnv = { BUTLER_OWNER_WECHAT_ID: "u-owner" }

  it("routes /诊断 to the owner-only diagnostics reply", async () => {
    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-owner",
      content: "/诊断",
      env: ownerEnv,
    })
    expect(result?.reply).toContain("【系统诊断】")
  })

  it("ignores /日志 from non-owners", async () => {
    const result = await tryWechatInboundCommand({
      wiring: h.wiring,
      fromUserId: "u-stranger",
      content: "/日志",
      env: ownerEnv,
    })
    expect(result).toBeNull()
  })
})

describe("subagent commands", () => {
  it("shows usage for a bare /委派", async () => {
    const result = await tryWechatSubagentCommand({
      wiring: h.wiring,
      fromUserId: "u-sub",
      content: "/委派",
      env: h.env,
    })
    expect(result?.reply).toContain("用法")
  })

  it("shows recent delegations from the audit log", async () => {
    await h.wiring.runtimeStore.appendAuditEvent({
      auditId: "11111111-1111-4111-8111-111111111111",
      runId: null,
      conversationId: "c-wechat-u-sub",
      correlationId: "c-wechat-u-sub",
      action: "subagent.delegation",
      subject: "general",
      detail: {
        childConversationId: "child-c-wechat-u-sub-1",
        task: "smoke summary",
        capabilities: ["general"],
      },
      createdAt: new Date(),
    })
    const status = await tryWechatSubagentCommand({
      wiring: h.wiring,
      fromUserId: "u-sub",
      content: "/委派状态",
      env: h.env,
    })
    expect(status?.reply).toContain("最近委派")
    expect(status?.reply).toContain("smoke")
  })
})
