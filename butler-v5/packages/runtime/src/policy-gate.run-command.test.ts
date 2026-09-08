import { describe, expect, it } from "vitest"
import { classifyRunCommandArgvRisk } from "./policy-gate.js"

describe("classifyRunCommandArgvRisk", () => {
  it("read-only programs → low", () => {
    expect(classifyRunCommandArgvRisk(["ls"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["cat", "file.txt"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["head", "-n", "5", "file"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["grep", "needle", "hay.txt"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["rg", "needle"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["pwd"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["date"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["echo", "hi"])).toBe("low")
    expect(classifyRunCommandArgvRisk(["wc", "-l", "file"])).toBe("low")
  })

  it("write-capable programs → high", () => {
    expect(classifyRunCommandArgvRisk(["git", "status"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["git", "commit", "-m", "x"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["pnpm", "test"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["node", "script.js"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["python3", "main.py"])).toBe("high")
  })

  it("shell metachar in arg → high (defense in depth)", () => {
    expect(classifyRunCommandArgvRisk(["ls", "a;rm"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["cat", "$(whoami)"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["echo", "x|y"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["ls", "a&b"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["cat", "a`b`"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["ls", "a<b"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["ls", "a>b"])).toBe("high")
  })

  it("empty argv or non-array → high (fail-closed)", () => {
    expect(classifyRunCommandArgvRisk([])).toBe("high")
    expect(classifyRunCommandArgvRisk(undefined)).toBe("high")
    expect(classifyRunCommandArgvRisk("ls")).toBe("high") // not an array
    expect(classifyRunCommandArgvRisk(["ls", 123])).toBe("high") // non-string arg → fail-closed
  })

  it("unknown program → high (fail-closed)", () => {
    expect(classifyRunCommandArgvRisk(["sudo", "ls"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["curl", "evil"])).toBe("high")
    expect(classifyRunCommandArgvRisk(["rm"])).toBe("high")
  })
})
