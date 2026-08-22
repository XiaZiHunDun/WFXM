import { describe, expect, it } from "vitest"
import {
  buildSlirpInnerScript,
  buildSlirpIptablesCommands,
  parseProxyPort,
  resolveAllowlistDestinations,
  shellQuote,
  SLIRP_HOST_GATEWAY,
} from "./slirp-egress.js"

describe("slirp egress", () => {
  it("shellQuote escapes single quotes", () => {
    expect(shellQuote("a'b")).toBe("'a'\\''b'")
  })

  it("buildSlirpIptablesCommands allows gateway proxy port only", () => {
    const cmds = buildSlirpIptablesCommands({ allowHostGatewayPort: 8080 })
    expect(cmds.join("\n")).toContain(`${SLIRP_HOST_GATEWAY}`)
    expect(cmds.join("\n")).toContain("--dport 8080")
    expect(cmds[0]).toBe("iptables -w 5 -P OUTPUT DROP")
  })

  it("buildSlirpInnerScript wires slirp, iptables, and bwrap --share-net", () => {
    const script = buildSlirpInnerScript({
      bwrapPath: "bwrap",
      bwrapArgs: ["--die-with-parent", "--share-net", "--", "echo", "hi"],
      iptablesCommands: buildSlirpIptablesCommands({ allowHostGatewayPort: 9000 }),
      commandTimeoutSec: 5,
    })
    expect(script).toContain("slirp4netns --configure")
    expect(script).toContain("$IPTABLES -w 5 -P OUTPUT DROP")
    expect(script).toContain("--share-net")
    expect(script).toContain("echo")
  })

  it("parseProxyPort extracts port from proxy url", () => {
    expect(parseProxyPort("http://127.0.0.1:4567")).toBe(4567)
  })

  it("resolveAllowlistDestinations resolves literal IPs", async () => {
    const dests = await resolveAllowlistDestinations(["127.0.0.1:443"])
    expect(dests).toEqual([{ ip: "127.0.0.1", port: 443 }])
  })
})
