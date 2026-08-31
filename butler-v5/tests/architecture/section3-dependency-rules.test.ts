/**
 * Arch guard (D33-arch-align §3 依赖方向与端口硬规则): lock the
 * 6 hard rules in DESIGN §3 against implementation drift.
 *
 *   §3 硬规则 (line 98-117):
 *     1. 依赖方向单向向内核 — Core 只依赖 Ports 接口；具体实现由
 *        Composition Root 注入。
 *     2. Intake 不包含 Agent 规划、权限判断或业务状态机；出站
 *        格式化和发送属于 Outbound Channel driven adapter。
 *     3. 模型调用只经 Model Port；模型不能签发 Grant / 不能访问
 *        凭证 / 不能绕过 Policy Gate。
 *     4. Governance 不依赖具体 Channel、工具或 Provider SDK；
 *        Provider 不能绕过 Policy Gate 回调核心状态。
 *     5. 两个外层（driving / driven）都要通过端口与核心交换；
 *        不存在绕过 Port 的第三类接缝。
 *     6. Delivery shell（apps/api）是 driving adapter + Core 薄
 *        编排层的复合体；boundary 之内可直连 driven adapters，
 *        所有副作用经 PolicyGate + CapabilityRegistry 收口。
 *
 * D26A + D8 already locked several invariants this guard re-states:
 *   - §3 #1 = D26A §20 #2 (Core 不 import adapters)
 *   - §3 #3 = D26A §20 #3 (LLM Model Port uniqueness)
 *   - §3 #6 = D8 §20 #11 (single LLM-tool loop)
 *
 * D33 extends with the 3 remaining rules:
 *   - §3 #2 (Intake boundary)
 *   - §3 #4 (Governance SDK isolation)
 *   - §3 #5 (no third bypass)
 *
 * Audit findings (D33, 2026-08-31):
 *
 *   - Intake module (`apps/api/src/wechat-intake.ts`) is a parsing
 *     + normalization surface. It must not contain decision logic
 *     (Policy / state machine / agent planning).
 *   - `policy-gate.ts` (the canonical Governance surface) imports
 *     from `@butler/domain/governance/types` and `@butler/domain/
 *`; it does NOT import from `@butler/adapters` (no slack / wechat
 *     / external SDK reach-through).
 *   - apps/api doesn't open a third bypass: capability execution
 *     flows through `wiring.runEngine` / `runButlerLoop` →
 *     `registry.executeThroughBoundary(gate, ...)` (D26A #4 +
 *     D29 §9). No direct `registry.execute*` from apps/api outside
 *     the runButlerLoop closure.
 *
 * Static checks (no runtime):
 *   - Core (domain + runtime) has 0 imports of `@butler/adapters`
 *     or `packages/adapters` (D26A §20 #2 re-stated under §3 #1).
 *   - `apps/api/src/wechat-intake.ts` does NOT import
 *     `PolicyGate` / `decidePermission` / `decidePolicy` /
 *     `CapabilityRegistry` (i.e. no decision logic).
 *   - `apps/api` does NOT make any HTTP call to upstream LLM
 *     endpoints (D26A §20 #3 re-stated under §3 #3).
 *   - `policy-gate.ts` does NOT import from `@butler/adapters`,
 *     `@butler/persistence`, `slack`, `wechat`, `mcp`, etc.
 *   - apps/api does NOT call `registry.execute*` outside
 *     `wechat-inbound-butler.ts` (the canonical entry).
 *
 * Runtime behavior is verified by:
 *   - D26A §20 #1+#2+#3+#4 (RunEngine / Core / LLM / entry)
 *   - D8 §20 #11 (single LLM-tool loop)
 *   - existing capability-boundary.test.ts (canonical execution path)
 *
 * Remediation when this guard fires:
 *   - Core imports adapters: §3 #1 violation; remove the import.
 *   - Intake writes decision logic: §3 #2 violation; move the
 *     decision into Core.Application or Core.Domain.
 *   - apps/api direct LLM HTTP: §3 #3 violation; route through
 *     `LLMAdapter.complete` (D23).
 *   - policy-gate imports SDK: §3 #4 violation; remove — Governance
 *     must be SDK-independent.
 *   - apps/api bypasses runButlerLoop: §3 #5 violation; route through
 *     the canonical entry.
 */

import { describe, expect, it } from "vitest"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const DOMAIN_SRC = join(__dirname, "../../packages/domain/src")
const RUNTIME_SRC = join(__dirname, "../../packages/runtime/src")
const POLICY_GATE = join(RUNTIME_SRC, "policy-gate.ts")
const APPS_SRC = join(__dirname, "../../apps/api/src")
const WECHAT_INTAKE = join(APPS_SRC, "wechat-intake.ts")
const WECHAT_INBOUND_BUTLER = join(APPS_SRC, "wechat-inbound-butler.ts")

function listProductionTs(root: string): string[] {
  const out: string[] = []
  function walk(dir: string): void {
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

describe("arch: §3 依赖方向与端口 6 硬规则 (D33)", () => {
  // ── §3 #1 依赖方向单向向内核 ────────────────────────────────

  it("§3 #1: Core (domain + runtime) does NOT import adapters / persistence implementations (Composition Root injection)", () => {
    const files = [...listProductionTs(DOMAIN_SRC), ...listProductionTs(RUNTIME_SRC)]
    const FORBIDDEN = [
      /from\s+["']@butler\/adapters\b/,
      /from\s+["'][^"']*packages\/adapters\b/,
      /from\s+["']@butler\/persistence\b/,
      /from\s+["'][^"']*packages\/persistence\b/,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `§3 #1: Core must NOT import adapters / persistence — Composition Root (bootstrap-wiring.ts) owns wiring: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §3 #2 Intake 不含 Agent 规划 / 权限判断 / 业务状态机 ──────

  it("§3 #2: wechat-intake (Intake) does NOT import PolicyGate / decision helpers (no agent planning / permission logic)", () => {
    const src = readFileSync(WECHAT_INTAKE, "utf-8")
    const FORBIDDEN = [
      /\bPolicyGate\b/,
      /\bCapabilityRegistry\b/,
      /\bdecidePermission\b/,
      /\bdecidePolicy\b/,
      /\bActiveMainRunConflict\b/,
      /\bgrantMatchesAction\b/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(src)) violations.push(`wechat-intake: ${re}`)
    }
    expect(
      violations,
      `§3 #2: Intake must stay parsing / normalization only — no decision logic: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §3 #3 模型调用只经 Model Port ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

  it("§3 #3: apps/api does NOT directly call upstream LLM endpoints (model calls go through LLMAdapter.complete — D26A §20 #3)", () => {
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
      const stripped = src
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "")
      for (const re of FORBIDDEN) {
        if (re.test(stripped)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `§3 #3: apps/api must route model calls through LLMAdapter: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §3 #4 Governance 不依赖 Channel/工具/Provider SDK ─ ─ ─ ─

  it("§3 #4: policy-gate (Governance) does NOT import Channel / 工具 / Provider SDK (SDK-isolated rule)", () => {
    const src = readFileSync(POLICY_GATE, "utf-8")
    const FORBIDDEN = [
      /from\s+["']@butler\/adapters\b/,
      /from\s+["']@butler\/persistence\b/,
      /from\s+["'][^"']*packages\/adapters\b/,
      /from\s+["'][^"']*packages\/persistence\b/,
      /from\s+["'][^"']*\/slack\b/,
      /from\s+["'][^"']*\/wechat\b/,
      /from\s+["'][^"']*\/mcp\b/,
      /from\s+["']axios\b/,
      /from\s+["']node-fetch\b/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(src)) violations.push(`policy-gate: ${re}`)
    }
    expect(
      violations,
      `§3 #4: Governance (policy-gate) must be SDK-independent: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §3 #5 不存在绕过 Port 的第三类接缝 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

  it("§3 #5: apps/api does NOT invoke registry.execute* outside the canonical runButlerLoop entry (no third bypass)", () => {
    // The canonical Capability execution path goes through
    // `registry.executeThroughBoundary(gate, request, ...)` from
    // wechat-inbound-butler.ts. Any apps/api file that calls
    // `registry.execute*` (or otherwise opens a Capability path)
    // outside that closure is a §3 #5 bypass.
    const files = listProductionTs(APPS_SRC).filter(
      (f) => f !== WECHAT_INBOUND_BUTLER,
    )
    const FORBIDDEN = [
      /(?<!\w)registry\.execute\w*\s*\(/,
      /(?<!\w)registry\.register\s*\(/,
      /(?<!\w)gate\.decide\s*\(/,
      /(?<!\w)gate\.evaluate\s*\(/,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `§3 #5: apps/api must not bypass runButlerLoop: ${violations.join(", ")}`,
    ).toEqual([])
  })

  // ── §3 #6 Delivery shell 不另立第二套 Loop/Policy ─ ─ ─ ─ ─

  it("§3 #6: apps/api does NOT define a second LLM-tool loop or Policy gate (single canonical — D8 §20 #11)", () => {
    const files = listProductionTs(APPS_SRC)
    const FORBIDDEN = [
      // Forbidden: parallel loop / parallel policy / parallel engine.
      /^(?:export\s+)?class\s+\w*(?:Loop|LoopEngine|ConversationEngine|Orchestrator)\b/m,
      /^(?:export\s+)?class\s+\w*PolicyGate\b/m,
      /^(?:export\s+)?class\s+\w*Engine\b/m,
    ]
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, "utf-8")
      for (const re of FORBIDDEN) {
        if (re.test(src)) violations.push(`${file}: ${re}`)
      }
    }
    expect(
      violations,
      `§3 #6: apps/api must not define a parallel Loop / Policy / Engine: ${violations.join(", ")}`,
    ).toEqual([])
  })
})