// Anchors: there is exactly one RunEngine, one PolicyGate, one CapabilityRegistry,
// and every side effect goes through the capability boundary. Merged from the
// former §20 #1, §3 #5 and runTool throat guards.
import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")
const APPS_SRC = join(__dirname, "../../apps/api/src")
const RUN_ENGINE = join(RUNTIME_SRC, "run-engine.ts")
const POLICY_GATE = join(RUNTIME_SRC, "policy-gate.ts")
const CAPABILITY_BOUNDARY = join(RUNTIME_SRC, "capability-boundary.ts")
const BOOTSTRAP_WIRING = join(APPS_SRC, "bootstrap-wiring.ts")
const TOOL_BOUNDARY = join(APPS_SRC, "tool-boundary.ts")
const WECHAT_INBOUND_BUTLER = join(APPS_SRC, "wechat-inbound-butler.ts")

function listProductionTs(root: string): string[] {
  const out: string[] = []
  if (!existsSync(root)) return out
  for (const entry of readdirSync(root)) {
    const p = join(root, entry)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (entry === "node_modules" || entry === "dist" || entry === "_archive") continue
      out.push(...listProductionTs(p))
    } else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) {
      out.push(p)
    }
  }
  return out
}

function declaringFiles(root: string, className: string): string[] {
  const re = new RegExp(`^export\\s+class\\s+${className}\\b`, "m")
  return listProductionTs(root).filter((f) => re.test(readFileSync(f, "utf-8")))
}

describe("side-effect throat", () => {
  it("apps production sources must not call runTool directly", () => {
    const violations = listProductionTs(APPS_SRC).filter((f) => {
      const src = readFileSync(f, "utf-8")
      return /\brunTool\b/.test(src) && /from\s+["']@butler\/runtime\/tool-runtime/.test(src)
    })
    expect(violations).toEqual([])
  })

  it("RunEngine / PolicyGate / CapabilityRegistry are declared exactly once", () => {
    expect(declaringFiles(RUNTIME_SRC, "RunEngine")).toEqual([RUN_ENGINE])
    expect(declaringFiles(RUNTIME_SRC, "PolicyGate")).toEqual([POLICY_GATE])
    expect(declaringFiles(RUNTIME_SRC, "CapabilityRegistry")).toEqual([POLICY_GATE])
  })

  it("singletons are constructed only in the composition root / canonical boundary", () => {
    const runtimeFiles = listProductionTs(RUNTIME_SRC)
    const registryCtors = runtimeFiles.filter((f) =>
      /new\s+CapabilityRegistry\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(registryCtors).toEqual([CAPABILITY_BOUNDARY])

    const appFiles = listProductionTs(APPS_SRC)
    expect(appFiles.filter((f) => /new\s+RunEngine\s*\(/.test(readFileSync(f, "utf-8")))).toEqual([
      BOOTSTRAP_WIRING,
    ])
    expect(appFiles.filter((f) => /new\s+PolicyGate\s*\(/.test(readFileSync(f, "utf-8")))).toEqual([
      TOOL_BOUNDARY,
    ])
    expect(
      appFiles.filter((f) =>
        /createProductionCapabilityRegistry\s*\(/.test(readFileSync(f, "utf-8")),
      ),
    ).toEqual([TOOL_BOUNDARY])
  })

  it("no apps file bypasses the canonical entry with registry.execute* / gate.decide", () => {
    const forbidden = [
      /(?<!\w)registry\.execute\w*\s*\(/,
      /(?<!\w)registry\.register\s*\(/,
      /(?<!\w)gate\.decide\s*\(/,
      /(?<!\w)gate\.evaluate\s*\(/,
    ]
    const violations: string[] = []
    for (const file of listProductionTs(APPS_SRC).filter((f) => f !== WECHAT_INBOUND_BUTLER)) {
      const src = readFileSync(file, "utf-8")
      for (const re of forbidden) {
        if (re.test(src)) violations.push(`${file}: ${re.source}`)
      }
    }
    expect(violations).toEqual([])
  })
})
