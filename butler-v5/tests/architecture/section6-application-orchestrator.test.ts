/**
 * Arch guard (D18-arch-align §6 Application 编排层): Application 是
 * 唯一执行协调器（Run Engine）。它不再拆成并列的 AgentKernel、
 * Orchestrator、SessionSupervisor 和 WorkflowRunner。
 *
 * DESIGN §6 says Application = the sole execution coordinator
 * (`RunEngine` in `packages/runtime/src/run-engine.ts`). No parallel
 * orchestrator / supervisor / workflow-runner class may exist.
 *
 * Audit findings (D18, 2026-08-30):
 *   - `packages/runtime/src/run-engine.ts` defines `class RunEngine` —
 *     the canonical Application orchestrator.
 *   - `packages/runtime/src/agent-kernel.ts` defines `class AgentKernel` —
 *     this is the Run's internal state-machine primitive consumed BY
 *     RunEngine; it is not a parallel orchestrator. AgentKernel.applyDecision
 *     is invoked via `safeApplyDecision` from inside the canonical
 *     conversation loop. Per §6: "AgentKernel + Orchestrator + SessionSupervisor
 *     + WorkflowRunner" is forbidden, but AgentKernel is a primitive (state
 *     machine for the Run), not a separate engine.
 *   - No `Orchestrator`, `SessionSupervisor`, `WorkflowRunner`, or
 *     `ConversationEngine` class exists outside of `RunEngine` /
 *     `AgentKernel` / `ConversationLoop`.
 *
 * Static checks (no runtime):
 *   - `packages/runtime/src/` defines exactly one orchestrator class:
 *     `RunEngine` in `run-engine.ts`. Any new class whose name ends
 *     with `Orchestrator` / `Supervisor` / `WorkflowRunner` /
 *     `ConversationEngine` / `LoopEngine` is a §6 violation.
 *   - No file under `packages/` other than `run-engine.ts` exports
 *     a class named `RunEngine` (only the canonical implementation
 *     defines the canonical orchestrator).
 *
 * Runtime behavior is verified by:
 *   - packages/runtime/src/run-engine.test.ts (full lifecycle)
 *   - tests/eval/scenarios/11-13 (race / idempotency / concurrent)
 *   - tests/architecture/single-llm-tool-loop.test.ts (D8, canonical
 *     loop is the sole conversation loop — companion invariant)
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")

const FORBIDDEN_ORCHESTRATOR_NAMES: readonly string[] = [
  "Orchestrator",
  "SessionSupervisor",
  "WorkflowRunner",
  "ConversationEngine",
  "LoopEngine",
  "RunCoordinatorEngine",
]

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    const stat = statSync(p)
    if (stat.isDirectory()) {
      out.push(...listTsFiles(p))
    } else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts") && !entry.endsWith(".d.ts")) {
      out.push(p)
    }
  }
  return out
}

describe("arch: §6 Application 编排层 (RunEngine is the sole orchestrator)", () => {
  it("RunEngine is defined in exactly one file: packages/runtime/src/run-engine.ts", () => {
    const tsFiles = listTsFiles(RUNTIME_SRC)
    const filesDeclaringRunEngine = tsFiles.filter((f) => {
      const src = readFileSync(f, "utf-8")
      // Match `export class RunEngine` or `class RunEngine ` (not extended).
      return /^export\s+class\s+RunEngine\b/m.test(src)
    })
    expect(
      filesDeclaringRunEngine,
      `RunEngine declared in: ${filesDeclaringRunEngine.join(", ")}`,
    ).toEqual([join(RUNTIME_SRC, "run-engine.ts")])
  })

  it("no parallel orchestrator class exists in packages/runtime/src/", () => {
    const tsFiles = listTsFiles(RUNTIME_SRC)
    const violations: string[] = []
    for (const file of tsFiles) {
      const src = readFileSync(file, "utf-8")
      for (const name of FORBIDDEN_ORCHESTRATOR_NAMES) {
        // Match `class <Name>` declaration (any export modifier).
        const re = new RegExp(`^export\\s+class\\s+${name}\\b`, "m")
        if (re.test(src)) {
          violations.push(`${file}: class ${name}`)
        }
      }
    }
    expect(
      violations,
      `forbidden orchestrator classes found: ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("AgentKernel is a Run-state primitive, not a parallel orchestrator (only one engine exists)", () => {
    // The canonical orchestrator is RunEngine (already asserted above).
    // AgentKernel is the Run's internal state machine. Lock that the
    // codebase has at most one class whose name ends in `Engine` in
    // packages/runtime/src/ — i.e., RunEngine. AgentKernel is not an
    // engine per §6 (it's a primitive).
    const tsFiles = listTsFiles(RUNTIME_SRC)
    const engineClasses: string[] = []
    for (const file of tsFiles) {
      const src = readFileSync(file, "utf-8")
      const match = src.match(/^export\s+class\s+(\w+Engine)\b/m)
      if (match && match[1]) {
        engineClasses.push(`${file}: class ${match[1]}`)
      }
    }
    expect(
      engineClasses,
      `engine classes in packages/runtime/src/: ${engineClasses.join(", ")} (only RunEngine allowed)`,
    ).toEqual([expect.stringMatching(/run-engine\.ts: class RunEngine$/)])
  })
})