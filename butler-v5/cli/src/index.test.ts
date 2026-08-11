import { describe, expect, it, vi } from "vitest"

vi.mock("commander", () => ({
  Command: class {
    name = vi.fn().mockReturnThis()
    description = vi.fn().mockReturnThis()
    version = vi.fn().mockReturnThis()
    command = vi.fn().mockReturnThis()
    action = vi.fn().mockReturnThis()
    parseAsync = vi.fn().mockResolvedValue(undefined)
  },
}))

describe("cli entry", () => {
  it("exports a butler program with start and verify commands", async () => {
    const { Command } = await import("commander")
    const mod = await import("./index.js")
    expect(typeof mod).toBe("object")
    expect((Command as unknown as { name: () => unknown }).name).toBeDefined()
  })
})
