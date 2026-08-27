import { describe, it, expect } from "vitest"
import { Effect } from "effect"
import { MockMCPDiscoveryLive } from "./index.js"
import { MCPDiscovery } from "@butler/ports"

describe("infrastructure/mcp", () => {
  it("discover returns tools", async () => {
    const program = Effect.gen(function* () {
      const mcp = yield* MCPDiscovery
      return yield* mcp.discover()
    })

    const result = await Effect.runPromise(Effect.provide(program, MockMCPDiscoveryLive))
    expect(result).toHaveLength(2)
    expect(result[0]?.name).toBe("read_file")
    expect(result[1]?.name).toBe("write_file")
  })

  it("invalidate returns void", async () => {
    const program = Effect.gen(function* () {
      const mcp = yield* MCPDiscovery
      yield* mcp.invalidate("server-1")
      return true
    })

    const result = await Effect.runPromise(Effect.provide(program, MockMCPDiscoveryLive))
    expect(result).toBe(true)
  })
})
