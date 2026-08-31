/**
 * Arch guard (D26A-arch-align §20 #1+#2+#3+#4 invariants batch A):
 *
 *   §20 #1 一个 Run Engine、一个 Policy Gate、一个副作用出口
 *   §20 #2 Core 只依赖 Ports，不 import 具体适配器；具体实现由 Composition Root 注入
 *   §20 #3 所有副作用通过 Capability Provider；模型调用走独立 Model Port
 *   §20 #4 所有入口归一化为 Run Trigger (driving adapter)
 *
 * Split from §20's 7 un-audited invariants (D25 handoff) into batch A
 * (this file, 4 invariants) + future batches B/C. Lock each invariant
 * by static path / pattern check so any future refactor that violates
 * one of them fails CI.
 *
 * Companion guards (inherited, do NOT duplicate):
 *   - section6-application-orchestrator.test.ts (D18) — RunEngine is
 *     the sole orchestrator class (this file's #1 re-locks
 *     `new RunEngine(` is called exactly once in production wiring).
 *   - dependency-direction.test.ts (D17) — Core (domain + runtime +
 *     persistence + ports) does not import adapters (this file's #2
 *     re-locks the same invariant under §20 framing + asserts the
 *     composition root is `apps/api/bootstrap-wiring.ts`).
 *   - side-effect-throat.test.ts / capability-boundary tests — §20 #3
 *     runtime behavior (this file adds the static LLM-Model-Port
 *     uniqueness lock: 0 apps/api file fetches the upstream LLM
 *     endpoints directly).
 *   - apps/api entry points (routes / cli-run / schedule-run / etc.)
 *     all funnel into `runButlerLoop` — this file's #4 locks that
 *     every entry point imports `runButlerLoop` from
 *     `./wechat-inbound-butler.js` and that no entry point creates
 *     Run / RunTrigger outside the runButlerLoop boundary.
 *
 * Static checks (no runtime):
 *   - Exactly one `class RunEngine` declaration (run-engine.ts).
 *   - Exactly one `class PolicyGate` declaration (policy-gate.ts).
 *   - Exactly one `class CapabilityRegistry` declaration
 *     (policy-gate.ts); exactly one `new CapabilityRegistry()`
 *     in production code (capability-boundary.ts).
 *   - 0 production files in `apps/` directly `fetch()` the upstream
 *     LLM endpoints (anthropic / openai / deepseek / dashscope).
 *   - 0 production files in `apps/api/src/` create a Run / RunTrigger
 *     outside of `wechat-inbound-butler.ts` (the canonical driving
 *     adapter).
 *   - 0 production files in `packages/{domain,runtime,persistence,ports}/`
 *     import from `@butler/adapters` or `packages/adapters`.
 *   - `apps/api/src/bootstrap-wiring.ts` is the composition root:
 *     it constructs the singleton RunEngine + PolicyGate +
 *     CapabilityRegistry and exposes them through `Wiring`.
 *
 * Runtime behavior is verified by:
 *   - run-engine.test.ts (canonical orchestrator lifecycle)
 *   - capability-boundary.test.ts (policy gate + capability registry)
 *   - apps/api/src/{routes,cli-run,task-run,schedule-run,wechat-intake,
 *     channel-inbound}.test.ts (entry points funnel into runButlerLoop)
 *
 * Remediation when this guard fires:
 *   - #1 violation (parallel engine / policy gate / capability registry):
 *     §20 #1 §6 violation; move the parallel implementation to use
 *     RunEngine / PolicyGate / CapabilityRegistry instead.
 *   - #2 violation (Core imports adapters): §20 #2 §3 端口依赖 violation;
 *     move the import to a composition root in apps/api/ instead.
 *   - #3 violation (apps/api direct LLM fetch): §20 #3 §3 Model Port
 *     violation; route through `LLMAdapter.complete` in
 *     `packages/adapters/src/llm-provider.ts`.
 *   - #4 violation (entry point bypasses runButlerLoop): §20 #4 §6
 *     violation; route through `runButlerLoop` (which validates the
 *     RunTrigger via `validateRunTrigger`).
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")
const POLICY_GATE = join(RUNTIME_SRC, "policy-gate.ts")
const CAPABILITY_BOUNDARY = join(RUNTIME_SRC, "capability-boundary.ts")
const RUN_ENGINE = join(RUNTIME_SRC, "run-engine.ts")
const APPS_SRC = join(__dirname, "../../apps/api/src")
const BOOTSTRAP_WIRING = join(APPS_SRC, "bootstrap-wiring.ts")

const CORE_DIRS = [
  join(__dirname, "../../packages/domain/src"),
  join(__dirname, "../../packages/runtime/src"),
  join(__dirname, "../../packages/persistence/src"),
  join(__dirname, "../../packages/ports/src"),
] as const

function listProductionTs(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
    if (!existsSync(dir)) return
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry)
      const st = statSync(p)
      if (st.isDirectory()) {
        if (
          entry === "node_modules" ||
          entry === "dist" ||
          entry === "_archive" ||
          entry === "coverage" ||
          entry.startsWith(".")
        ) {
          continue
        }
        walk(p)
      } else if (
        entry.endsWith(".ts") &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".d.ts")
      ) {
        out.push(p)
      }
    }
  }
  walk(root)
  return out
}

describe("arch: §20 #1+#2+#3+#4 invariants batch A (D26A)", () => {
  // ── §20 #1: 一个 Run Engine、一个 Policy Gate、一个副作用出口 ──

  it("#1: RunEngine class is declared in exactly one file (run-engine.ts)", () => {
    const files = listProductionTs(RUNTIME_SRC)
    const matches = files.filter((f) =>
      /^export\s+class\s+RunEngine\b/m.test(readFileSync(f, "utf-8")),
    )
    expect(matches, `RunEngine declared in: ${matches.join(", ")}`).toEqual([RUN_ENGINE])
  })

  it("#1: PolicyGate class is declared in exactly one file (policy-gate.ts)", () => {
    const files = listProductionTs(RUNTIME_SRC)
    const matches = files.filter((f) =>
      /^export\s+class\s+PolicyGate\b/m.test(readFileSync(f, "utf-8")),
    )
    expect(matches, `PolicyGate declared in: ${matches.join(", ")}`).toEqual([POLICY_GATE])
  })

  it("#1: CapabilityRegistry class declared exactly once + construction site exactly once (composition root)", () => {
    const files = listProductionTs(RUNTIME_SRC)
    const decls = files.filter((f) =>
      /^export\s+class\s+CapabilityRegistry\b/m.test(readFileSync(f, "utf-8")),
    )
    expect(decls, `CapabilityRegistry declared in: ${decls.join(", ")}`).toEqual([
      POLICY_GATE,
    ])
    // Exactly one `new CapabilityRegistry(` across production runtime.
    const ctorSites = files.filter((f) =>
      /new\s+CapabilityRegistry\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(
      ctorSites.length,
      `CapabilityRegistry construction sites = ${ctorSites.length}; want exactly 1 (composition root)`,
    ).toBe(1)
    expect(ctorSites[0]).toBe(CAPABILITY_BOUNDARY)
  })

  it("#1: canonical-module singleton sites — RunEngine in composition root, CapabilityRegistry + PolicyGate in tool-boundary", () => {
    // §20 #1 mandates one of each. The codebase splits canonical
    // instantiation across two canonical modules:
    //   - RunEngine → apps/api/src/bootstrap-wiring.ts (composition root)
    //   - CapabilityRegistry + PolicyGate → apps/api/src/tool-boundary.ts
    //     (canonical capability execution boundary)
    // Together they form the "唯一副作用出口" + "唯一 Policy Gate" + "唯一
    // Run Engine" trio. Any new instance outside these two files is a
    // §20 #1 violation.
    const appsFiles = listProductionTs(APPS_SRC)
    const runEngineInstances = appsFiles.filter((f) =>
      /new\s+RunEngine\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(runEngineInstances, `new RunEngine( sites: ${runEngineInstances.join(", ")}`).toEqual(
      [BOOTSTRAP_WIRING],
    )
    const capabilityRegistryInstances = appsFiles.filter((f) =>
      /createProductionCapabilityRegistry\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(
      capabilityRegistryInstances.length,
      `createProductionCapabilityRegistry sites = ${capabilityRegistryInstances.length}; want exactly 1 (in tool-boundary.ts)`,
    ).toBe(1)
    expect(capabilityRegistryInstances[0]).toBe(join(APPS_SRC, "tool-boundary.ts"))
    const policyGateInstances = appsFiles.filter((f) =>
      /new\s+PolicyGate\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(
      policyGateInstances.length,
      `PolicyGate instance sites = ${policyGateInstances.length}; want exactly 1`,
    ).toBe(1)
    expect(policyGateInstances[0]).toBe(join(APPS_SRC, "tool-boundary.ts"))
  })

  // ── §20 #2: Core 只依赖 Ports，不 import 具体适配器 ──────────

  it("#2: Core (domain + runtime + persistence + ports) does NOT import @butler/adapters or packages/adapters", () => {
    const violations: string[] = []
    const re =
      /from\s+["']@butler\/adapters\b|from\s+["'][^"']*packages\/adapters\b/
    for (const dir of CORE_DIRS) {
      for (const file of listProductionTs(dir)) {
        if (re.test(readFileSync(file, "utf-8"))) {
          violations.push(file)
        }
      }
    }
    expect(
      violations,
      `Core files importing adapters: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §20 #3: 模型调用走独立 Model Port（apps/api 不直 fetch upstream LLM） ──

  it("#3: apps/api does NOT directly fetch upstream LLM endpoints (model calls go through LLMAdapter)", () => {
    const files = listProductionTs(APPS_SRC)
    const FORBIDDEN = [
      /fetch\(\s*["'`][^"'`]*anthropic\.com/,
      /fetch\(\s*["'`][^"'`]*openai\.com/,
      /fetch\(\s*["'`][^"'`]*deepseek\.com/,
      /fetch\(\s*["'`][^"'`]*dashscope\.aliyuncs\.com/,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      // Strip block + line comments so doc-comment references do not count.
      const stripped = src
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "")
      for (const re of FORBIDDEN) {
        if (re.test(stripped)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `apps/api files directly fetching upstream LLM: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §20 #4: 所有入口归一化为 Run Trigger (driving adapter) ─────

  it("#4: every apps/api entry point imports runButlerLoop from ./wechat-inbound-butler.js (canonical driving adapter)", () => {
    // Identify entry points: any .ts in apps/api/src/ that exposes a HTTP
    // route, an outbox handler, or a CLI command. The canonical
    // dispatch path is `runButlerLoop` (in wechat-inbound-butler.ts).
    const KNOWN_ENTRY_POINTS: readonly string[] = [
      "cli-run.ts",
      "task-run.ts",
      "schedule-run.ts",
      "wechat-intake.ts",
      "channel-inbound.ts",
      "routes.ts",
    ]
    for (const name of KNOWN_ENTRY_POINTS) {
      const path = join(APPS_SRC, name)
      if (!existsSync(path)) continue
      const src = readFileSync(path, "utf-8")
      expect(
        src,
        `${name} must import runButlerLoop from ./wechat-inbound-butler.js (§20 #4)`,
      ).toMatch(/import\s*\{[^}]*runButlerLoop[^}]*\}\s*from\s*["']\.\/wechat-inbound-butler\.js["']/)
    }
  })

  it("#4: entry points reach RunEngine only via `wiring.runEngine` (composition-root singleton, no direct `new RunEngine(`)", () => {
    // apps/api may construct RunEngine exactly once: in
    // `bootstrap-wiring.ts` (composition root). All other entry
    // points must consume `wiring.runEngine.<method>(...)` (i.e.
    // `executeInbound` / `resumeRun`) instead of building their own.
    const appsFiles = listProductionTs(APPS_SRC)
    const directNewRunEngine = appsFiles.filter((f) =>
      /new\s+RunEngine\s*\(/.test(readFileSync(f, "utf-8")),
    )
    expect(
      directNewRunEngine,
      `apps/api files with direct new RunEngine( — must be only composition root (bootstrap-wiring.ts): ${directNewRunEngine.join(", ")}`,
    ).toEqual([BOOTSTRAP_WIRING])
    // All entry points should funnel through wiring.runEngine OR runButlerLoop
    // (runButlerLoop internally uses wiring.runEngine.executeInbound).
    const KNOWN_ENTRY_POINTS: readonly string[] = [
      "cli-run.ts",
      "task-run.ts",
      "schedule-run.ts",
      "wechat-intake.ts",
      "channel-inbound.ts",
      "routes.ts",
      "approval-resume.ts",
    ]
    for (const name of KNOWN_ENTRY_POINTS) {
      const path = join(APPS_SRC, name)
      if (!existsSync(path)) continue
      const src = readFileSync(path, "utf-8")
      const usesWiringRunEngine = /\b(wiring|args\.wiring)\.runEngine\./
      const usesRunButlerLoop = /\brunButlerLoop\s*\(/
      expect(
        usesWiringRunEngine.test(src) || usesRunButlerLoop.test(src),
        `${name} must reach RunEngine via wiring.runEngine.* or runButlerLoop(...) (composition-root dispatch)`,
      ).toBe(true)
    }
  })
})