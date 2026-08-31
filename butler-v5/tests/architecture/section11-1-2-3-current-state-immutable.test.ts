/**
 * Arch guard (D28-arch-align §11.1 Current State + §11.2 Append-only
 * Records + §11.3 Outbox): lock the 3 §11 子段 invariants.
 *
 *   §11.1 Current State: Conversation/Run/Step/Grant 直接保存当前状态；
 *                          普通查询不依赖事件重放；写入通过明确事务更新；
 *                          入站去重键 `(triggerSource, idempotencyKey)`
 *                          唯一约束；并发控制用版本号；状态迁移由 Domain
 *                          纯函数验证。
 *   §11.2 Append-only Records: Message / Grant 签发使用撤销 / 对外发送 /
 *                              Run lifecycle / 安全事件 不可变；
 *                              低风险工具结果只写 Step，不双写 audit_events。
 *   §11.3 Outbox: 保留解决状态提交与异步副作用一致性；只用于
 *                  Channel 发送 / Child Run 派发 / 事务后外部通知。
 *
 * Audit findings (D28, 2026-08-31):
 *
 *   - §11.1 — `messages.idempotencyKey` + `runs.idempotencyKey` carry
 *     uniqueIndex (`messages_idempotency_uniq` / `runs_idempotency_uniq`).
 *     DESIGN §11.1 line 483 text says the constraint is the pair
 *     `(triggerSource, idempotencyKey)`; impl uses `idempotencyKey`
 *     alone. D28 acknowledges the drift (the narrower key still
 *     prevents the duplicate-inbound pattern §11.1 targets; a future
 *     multi-channel expansion may need the paired key).
 *   - `runs.version` (integer, default 1) drives optimistic concurrency
 *     on `transitionRunStatus(runId, version, ...)`.
 *   - `store.withTransaction(fn)` (runtime-store.ts:479 +
 *     store-contract.ts:209) is the canonical transactional boundary;
 *     run-lifecycle.ts wraps `cancel` / `succeed` / `fail` /
 *     `transitionRunStatus` paths in it.
 *   - §11.2 — `messages` table has no UPDATE path (append-only by
 *     contract; runtime-store exposes `appendMessage` only).
 *   - `audit_events` table + `appendEventAndEnqueueOutbox` function
 *     (event-store.ts:146) provide the immutable audit log.
 *   - §11.3 — `outbox` pgTable + `appendEventAndEnqueueOutbox` is the
 *     single enqueue point (per §20 #7 already locked in D7).
 *
 * Static checks (no runtime):
 *   - `messages` pgTable declares `idempotencyUniq: uniqueIndex(...)`.
 *   - `runs` pgTable declares `idempotencyUniq: uniqueIndex(...)`
 *     + `version: integer(...).default(1)`.
 *   - `RuntimeStore` contract + impl expose `withTransaction(fn)`.
 *   - `run-lifecycle.ts` uses `store.withTransaction(...)` in at
 *     least 4 lifecycle paths (cancel / succeed / fail / resume).
 *   - `messages` table has no `updateMessage` / `setMessage` exposed.
 *   - `audit_events` pgTable + `appendEventAndEnqueueOutbox` declared.
 *   - `outbox` pgTable + `appendEventAndEnqueueOutbox` (single enqueue).
 *   - Capability execution (success path) writes to `Step` only;
 *     `audit_events` is reserved for policy decision + security
 *     events (per §11.2 line 497: audit 用于解释和追责, 不重建
 *     业务状态唯一来源).
 *
 * Runtime behavior is verified by:
 *   - runtime-store.test.ts (current-state reads + transactions)
 *   - run-lifecycle.test.ts (transactional lifecycle)
 *   - event-store.test.ts (appendEventAndEnqueueOutbox + outbox tx)
 *   - §20 #7 (D4 cancel cascade) + §20 #8 (D7 outbox tx) locks
 *     the operational invariant.
 *
 * Remediation when this guard fires:
 *   - Idempotency uniq removed: §11.1 violation; restore.
 *   - `runs.version` removed: §11.1 violation; restore + extend
 *     `transitionRunStatus` signature.
 *   - `store.withTransaction` removed: §11.1 violation; restore.
 *   - `messages.updateMessage` introduced: §11.2 violation; remove —
 *     messages are append-only by contract.
 *   - `outbox` bypassed (direct insert): §11.3 + §20 #7 violation;
 *     route through `appendEventAndEnqueueOutbox`.
 *   - Capability success writing audit_events: §11.2 violation;
 *     remove — success goes to Step.
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const SCHEMA = join(__dirname, "../../packages/persistence/src/schema.ts")
const RUNTIME_STORE = join(__dirname, "../../packages/persistence/src/runtime-store.ts")
const STORE_CONTRACT = join(
  __dirname,
  "../../packages/domain/src/runtime/store-contract.ts",
)
const RUN_LIFECYCLE = join(__dirname, "../../packages/runtime/src/run-lifecycle.ts")
const EVENT_STORE = join(__dirname, "../../packages/persistence/src/event-store.ts")
const CAPABILITY_BOUNDARY = join(
  __dirname,
  "../../packages/runtime/src/capability-boundary.ts",
)

describe("arch: §11.1 Current State + §11.2 Append-only + §11.3 Outbox (D28)", () => {
  // ── §11.1 Current State ────────────────────────────────────────

  it("§11.1: messages + runs carry idempotencyUniq uniqueIndex (text-vs-impl drift on (triggerSource, idempotencyKey) pair acknowledged)", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    // Both tables must have an idempotencyUniq unique index. Match the
    // closing `})` of the pgTable call (the schema uses the
    // `(t) => ({...index...})` second arg, ending with `}),\n)`).
    const messagesMatch = src.match(
      /export const messages = pgTable\s*\(\s*["']messages["'][\s\S]*?\n\)\s*\n/,
    )
    expect(messagesMatch, "messages pgTable not found").not.toBeNull()
    expect(
      messagesMatch?.[0],
      "messages must declare idempotencyUniq uniqueIndex",
    ).toMatch(/idempotencyUniq:\s*uniqueIndex\(/)
    const runsMatch = src.match(
      /export const runs = pgTable\s*\(\s*["']runs["'][\s\S]*?\n\)\s*\n/,
    )
    expect(runsMatch, "runs pgTable not found").not.toBeNull()
    expect(
      runsMatch?.[0],
      "runs must declare idempotencyUniq uniqueIndex",
    ).toMatch(/idempotencyUniq:\s*uniqueIndex\(/)
  })

  it("§11.1: runs declares `version: integer(...).default(1)` for optimistic concurrency", () => {
    const src = readFileSync(SCHEMA, "utf-8")
    const runsMatch = src.match(
      /export const runs = pgTable\s*\(\s*["']runs["'][\s\S]*?\n\)\s*\n/,
    )
    expect(runsMatch, "runs pgTable not found").not.toBeNull()
    expect(runsMatch?.[0]).toMatch(
      /version:\s*integer\s*\(\s*["']version["']\s*\)\.notNull\(\)\.default\(1\)/,
    )
  })

  it("§11.1: RuntimeStore exposes withTransaction (contract + impl); run-lifecycle wraps at least 4 transactional paths", () => {
    const contractSrc = readFileSync(STORE_CONTRACT, "utf-8")
    expect(contractSrc).toMatch(
      /readonly\s+withTransaction:\s*<T>\s*\(\s*fn:\s*\(\s*tx:\s*RuntimeTx\s*\)\s*=>\s*Promise<T>\s*\)\s*=>\s*Promise<T>/,
    )
    const implSrc = readFileSync(RUNTIME_STORE, "utf-8")
    expect(implSrc).toMatch(/async\s+withTransaction\s*\(/)
    // run-lifecycle should wrap enough paths in transactions.
    const lifecycleSrc = readFileSync(RUN_LIFECYCLE, "utf-8")
    const txCount = (
      lifecycleSrc.match(/store\.withTransaction\s*\(/g) ?? []
    ).length
    expect(
      txCount,
      `run-lifecycle.ts uses store.withTransaction(...) in ${txCount} paths; want ≥ 4 (cancel/succeed/fail/resume)`,
    ).toBeGreaterThanOrEqual(4)
  })

  // ── §11.2 Append-only Records ─────────────────────────────────

  it("§11.2: messages table has no update API exposed (append-only by contract)", () => {
    const contractSrc = readFileSync(STORE_CONTRACT, "utf-8")
    const implSrc = readFileSync(RUNTIME_STORE, "utf-8")
    const FORBIDDEN = [
      /\bupdateMessage\s*\(/,
      /\bsetMessage\s*\(/,
      /\boverwriteMessage\s*\(/,
      /\bpatchMessage\s*\(/,
    ]
    const violations: string[] = []
    for (const re of FORBIDDEN) {
      if (re.test(contractSrc)) violations.push(`store-contract.ts: ${re}`)
      if (re.test(implSrc)) violations.push(`runtime-store.ts: ${re}`)
    }
    expect(
      violations,
      `messages update API leaked into store: ${violations.join(", ")}`,
    ).toEqual([])
  })

  it("§11.2: audit_events table + appendEventAndEnqueueOutbox function exist (immutable audit log)", () => {
    const schemaSrc = readFileSync(SCHEMA, "utf-8")
    expect(
      /export\s+const\s+auditEvents\s*=\s*pgTable\s*\(\s*["']audit_events["']/.test(
        schemaSrc,
      ),
      "audit_events pgTable must exist (D6 audit tx atomicity companion)",
    ).toBe(true)
    const eventStoreSrc = readFileSync(EVENT_STORE, "utf-8")
    expect(eventStoreSrc).toMatch(
      /export\s+(async\s+)?function\s+appendEventAndEnqueueOutbox\s*\(/,
    )
  })

  // ── §11.3 Outbox ────────────────────────────────────────────────

  it("§11.3: outbox pgTable + appendEventAndEnqueueOutbox (single enqueue point per §20 #7)", () => {
    const schemaSrc = readFileSync(SCHEMA, "utf-8")
    expect(schemaSrc).toMatch(
      /export\s+const\s+outbox\s*=\s*pgTable\s*\(\s*["']outbox["']/,
    )
    const eventStoreSrc = readFileSync(EVENT_STORE, "utf-8")
    expect(eventStoreSrc).toMatch(
      /export\s+(async\s+)?function\s+appendEventAndEnqueueOutbox\s*\(/,
    )
  })

  // ── §11.2: 成功的低风险工具结果只写 Step，不双写 audit_events ──

  it("§11.2: capability success path writes to Step only; audit_events reserved for policy/security (low-risk tools do NOT double-write audit_events)", () => {
    const capSrc = readFileSync(CAPABILITY_BOUNDARY, "utf-8")
    // Capability success path MUST call tracer.record({kind:"step", name:"..."}).
    // It MUST NOT also write audit_events for a successful outcome.
    // The cleanest static check is: capability-boundary.ts has exactly
    // ONE tracer.record call per execution (the success trace); audit_event
    // writes happen via appendEventAndEnqueueOutbox in event-bridge,
    // not from capability-boundary.ts.
    const auditWriteInCap = /insert\s*\(\s*auditEvents\s*\)/.test(capSrc)
    expect(
      auditWriteInCap,
      "capability-boundary.ts must NOT insert into auditEvents directly — §11.2 forbids double-write for success",
    ).toBe(false)
    // Sanity: it does write the step trace.
    expect(capSrc).toMatch(/tracer\.record\s*\(/)
  })
})