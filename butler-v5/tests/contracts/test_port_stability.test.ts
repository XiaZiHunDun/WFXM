// tests/contracts/test_port_stability.test.ts
// 契约测试 — v5 Core Port 接口签名稳定性
// 验证每个 DESIGN §7 物化的 Core Port 端口可导入并导出预期符号。
//
// 历史：本测试曾校验 R2 时代的 14 个 Effect Tag 接口；2026-08-28 R12
// 简化方案让 R2 Effect Tag 体系归档至
// `_archive/packages/ports-effect-tag-scaffold/index.ts`，契约改测新的
// 6 个 Core Port 接口。

import { describe, it, expect } from "vitest"
import * as clockMod from "@butler/ports/core/clock.js"
import * as credentialMod from "@butler/ports/core/credential-provider.js"
import * as eventStoreMod from "@butler/ports/core/event-store.js"
import * as outboxMod from "@butler/ports/core/outbox.js"
import * as snapshotMod from "@butler/ports/core/snapshot.js"
import * as projectionMod from "@butler/ports/core/projection.js"

describe("v5 Core Port 模块可导入（DESIGN §7）", () => {
  // 仅 runtime 值（const / function）出现在 `import * as` namespace object；
  // interface（ClockPort / EventStorePort 等）是 TypeScript-only，编译消失。
  // 因此 runtime probe 只测 module 顶层的值导出（如 `systemClock`、
  // `memoryOutbox` 等），不试图断言 interface 名。
  const ports = [
    { name: "Clock", mod: clockMod, runtime: "systemClock" as const },
    { name: "CredentialProvider", mod: credentialMod, runtime: "isValidCredentialName" as const },
    { name: "EventStore", mod: eventStoreMod, runtime: undefined as undefined },
    { name: "Outbox", mod: outboxMod, runtime: "memoryOutbox" as const },
    { name: "Snapshot", mod: snapshotMod, runtime: "memorySnapshot" as const },
    { name: "Projection", mod: projectionMod, runtime: "memoryProjection" as const },
  ] as const

  for (const { name, mod, runtime } of ports) {
    it(`${name} 模块可导入${runtime ? ` + runtime ${runtime} 存在` : "（interface-only）"}`, () => {
      expect(mod, `${name} 模块 namespace 应存在`).toBeDefined()
      expect(typeof mod, `${name} 必须是 namespace object`).toBe("object")
      if (runtime) {
        expect(
          (mod as Record<string, unknown>)[runtime],
          `${name}.${runtime} runtime 值应存在`,
        ).toBeDefined()
      }
    })
  }
})

describe("v5 Core Port 总数", () => {
  it("DESIGN §7.1 物化 6 个 Core Port", () => {
    const total = [
      clockMod,
      credentialMod,
      eventStoreMod,
      outboxMod,
      snapshotMod,
      projectionMod,
    ].length
    expect(total).toBe(6)
  })
})
