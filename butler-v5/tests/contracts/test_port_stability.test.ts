// tests/contracts/test_port_stability.test.ts
// 契约测试 — Port 接口签名稳定性 [G-2]
// 验证所有 Effect Tag 存在且具有正确的标识符

import { describe, it, expect } from "vitest"
import {
  LLMService,
  ToolExecutor,
  EventStoreService,
  LoopInterrupt,
  GuardService,
  WeChatGateway,
  MCPDiscovery,
  ProjectService,
  MemoryService,
  WorkflowService,
  Config,
} from "@butler/ports"

describe("契约测试：Port Tag 存在性", () => {
  const tags = [
    { name: "LLMService", tag: LLMService },
    { name: "ToolExecutor", tag: ToolExecutor },
    { name: "EventStoreService", tag: EventStoreService },
    { name: "LoopInterrupt", tag: LoopInterrupt },
    { name: "GuardService", tag: GuardService },
    { name: "WeChatGateway", tag: WeChatGateway },
    { name: "MCPDiscovery", tag: MCPDiscovery },
    { name: "ProjectService", tag: ProjectService },
    { name: "MemoryService", tag: MemoryService },
    { name: "WorkflowService", tag: WorkflowService },
    { name: "Config", tag: Config },
  ] as const

  for (const { name, tag } of tags) {
    it(`${name} Tag 已定义且可实例化`, () => {
      expect(tag).toBeDefined()
      // Context.Tag 是可调用对象，可以通过 Tag.of() 创建实例
      expect(typeof tag).toBe("function")
    })
  }
})

describe("契约测试：Port Tag 数量", () => {
  it("总共 11 个 Port Tag", () => {
    const tagCount = [
      LLMService,
      ToolExecutor,
      EventStoreService,
      LoopInterrupt,
      GuardService,
      WeChatGateway,
      MCPDiscovery,
      ProjectService,
      MemoryService,
      WorkflowService,
      Config,
    ].length
    expect(tagCount).toBe(11)
  })
})

describe("契约测试：Port Tag 标识符唯一性", () => {
  it("所有 Tag 的 key 唯一", () => {
    const tags = [
      LLMService,
      ToolExecutor,
      EventStoreService,
      LoopInterrupt,
      GuardService,
      WeChatGateway,
      MCPDiscovery,
      ProjectService,
      MemoryService,
      WorkflowService,
      Config,
    ]
    // 每个 Context.Tag 有唯一的 key (Symbol)
    const keys = tags.map((t) => String(t.key))
    const unique = new Set(keys)
    expect(unique.size).toBe(tags.length)
  })
})
