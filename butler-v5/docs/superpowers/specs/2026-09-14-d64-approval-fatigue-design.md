# D64 — Approval Fatigue Mitigation（设计文档）

> 来源：D48 §3.1 结构性 gap（fixture harness 样本盲点 — owner 实测撞点）。D64 = owner 真撞启动批（prompt fatigue 撞点：连续 approve 后发现 1+ 不该批）。
>
> 范围：D64 = §3.1 mechanism 修复 — threshold + cooldown + checklist + audit fatigue_signal + replay + cross-channel 一致 + 3 acceptance scenarios。
>
> 性质：纯 additive，不改 inline-approval y/👌 现有 ergonomics（D44 product lock）；audit_event 扩展复用 D63 audit_event schema（correlation_id 不动）。

---

## 1. Architecture overview

```
inline approve request (wechat / telegram / CLI)
    ↓
    InlineApprovalPolicy.evaluate(tool_call, recent_audit)
      1. FatigueSignal(audit_log, window=60s) → { count, last_n_actions[] }
      2. SensitiveToolChecklist.match(tool_name) → required?
      3. decision matrix:
         a. tool.sensitivity = 'high' → CHECKLIST (must acknowledge)
         b. count >= 3 in 60s        → COOLDOWN (force wait 3s)
         c. else                     → ALLOW
    ↓
    if CHECKLIST → block + render checklist prompt → owner 勾 → proceed
    if COOLDOWN  → block + render wait indicator → sleep 3s → proceed
    if ALLOW     → proceed
    ↓
    execute tool + audit_event{ fatigue_signal?, cooldown_applied?, checklist_required? }
    (D63 audit_event schema extended; correlation_id 不动)

/v1/owner/audit/fatigue (extension to D44 audit replay)
    GET  → list 最近 60s 内连续 approve 序列
    POST /replay → 1-click 重审 / 撤销整序列
```

### 关键不变量

- D44 inline-approval y/👌 ergonomics 不变 — y/👌 仍然 1 token 通过（cooldown/checklist 在 y 之前拦截，不在 y 之后）
- D63 audit_event.correlation_id 行为不变 — fatigue_signal 作为 optional 字段加入
- D48 4 项产品力（诚实承认 gap / 结构化 reply / advice-not-action / 多 turn context）不退化 — FatigueSignal 失败 fail-safe allow + audit.degraded=true（不替 owner 决定）
- 跨 channel 一致行为 — wechat / telegram / CLI 共用 `lib/fatigue/policy.ts`
- 阈值硬编码 v1 — owner-tunable 在 D65+ scope（不在 D64）

---

## 2. Components & Data Structures

### 2.1 新增类型（`lib/fatigue/signal.ts`）

```typescript
/**
 * FatigueSignal = 滑动窗口内 approve 计数。
 *
 * 计算输入: audit_log (append-only D63 schema), window_seconds (default 60)
 * 计算输出: { count, window_seconds, last_n_actions: AuditEventSummary[] }
 *
 * 纯函数无副作用，便于 unit test。
 */
export interface FatigueSignal {
  readonly count: number
  readonly window_seconds: number
  readonly last_n_actions: ReadonlyArray<{
    readonly event_id: string
    readonly tool_name: string
    readonly actor: string
    readonly ts: number // ms epoch
    readonly decision: 'allow' | 'checklist' | 'cooldown'
  }>
  readonly degraded?: true // 读 audit log 失败时设置
}

export const DEFAULT_WINDOW_SECONDS = 60
export const DEFAULT_COUNT_THRESHOLD = 3

export function computeFatigueSignal(
  auditLog: AuditLogReader,
  windowSeconds: number = DEFAULT_WINDOW_SECONDS,
): FatigueSignal
```

### 2.2 新增类型（`lib/fatigue/policy.ts`）

```typescript
export type SensitivityLevel = 'high' | 'normal'

export type PolicyDecision =
  | { readonly action: 'allow' }
  | { readonly action: 'cooldown'; readonly duration_ms: number; readonly signal: FatigueSignal }
  | { readonly action: 'checklist'; readonly items: ReadonlyArray<string>; readonly signal: FatigueSignal }

export interface ToolSensitivity {
  readonly tool_name: string
  readonly level: SensitivityLevel
}

export const DEFAULT_COOLDOWN_MS = 3000
export const DEFAULT_CHECKLIST_TIMEOUT_MS = 60_000

export function evaluateInlineApproval(
  toolCall: { readonly tool_name: string; readonly args: Record<string, unknown> },
  recentAudit: AuditLogReader,
  sensitivity: ToolSensitivityRegistry,
): PolicyDecision
```

**决策矩阵**：

| tool.sensitivity | signal.count ≥ 3 (60s) | decision (单次 evaluate 返回) |
|---|---|---|
| high | yes | `cooldown` (3s) — caller sleep + re-evaluate |
| high | no | `checklist` |
| normal | yes | `cooldown` (3s) |
| normal | no | `allow` |

注: high + count≥3 走两轮 — 第 1 次 evaluate 返回 `cooldown`（caller sleep 3s 后再调），第 2 次 evaluate 因 count 已滚出 window 或不变返回 `checklist`。这样 checklist 拦截单独可见、audit_event 两个字段都填（cooldown_applied + checklist_required）。

### 2.3 新增类型（`lib/fatigue/checklist.ts`）

```typescript
export const HIGH_SENSITIVITY_TOOLS: ReadonlyArray<string> = [
  'send_*',         // send_email / send_message / send_wechat / send_telegram
  'delete_*',       // delete_file / delete_record / delete_candidate
  'external_write', // post / patch / put to external API
  'broadcast_*',    // broadcast_notice / broadcast_wechat / broadcast_telegram
]

/**
 * SensitiveToolChecklist = pattern match tool_name against HIGH_SENSITIVITY_TOOLS.
 * Returns required checklist items (1 line per item, owner must acknowledge each).
 */
export function matchSensitivity(
  toolName: string,
  registry: ToolSensitivityRegistry,
): { readonly level: SensitivityLevel; readonly items: ReadonlyArray<string> } | null

export const DEFAULT_CHECKLIST_ITEMS = [
  '我已读此操作的后果，且操作不可撤销。',
  '我确认目标对象正确（recipient / path / target）。',
]
```

### 2.4 AuditFatigueEvent（扩展 D63 schema）

```typescript
// D63 audit_event base (existing — 不动 correlation_id):
export interface AuditEvent {
  readonly event_id: string
  readonly correlation_id: string // D63 — unchanged
  readonly actor: string
  readonly tool_name: string
  readonly decision: 'allow' | 'deny'
  readonly ts: number
  readonly metadata?: Record<string, unknown>
  // ... D63 其他字段不变

  // NEW (D64) — 3 个 optional 字段 (additive, backward-compatible):
  readonly fatigue_signal?: {
    readonly count: number
    readonly window_seconds: number
    readonly last_n_actions: ReadonlyArray<{
      readonly event_id: string
      readonly tool_name: string
      readonly ts: number
    }>
    readonly degraded?: true
  }
  readonly cooldown_applied?: {
    readonly duration_ms: number
    readonly interrupted?: true // owner /cancel during wait
  }
  readonly checklist_required?: boolean
}
```

### 2.5 `/v1/owner/audit/fatigue`（扩展 D44 audit replay）

```typescript
// GET /v1/owner/audit/fatigue?window_seconds=60
//   → { sequences: Array<{ start_ts, end_ts, count, event_ids: string[] }> }
//   仅返回 count >= DEFAULT_COUNT_THRESHOLD 的连续 approve 序列
//   失败 → 200 + { sequences: [] } (不抛 5xx)

// POST /v1/owner/audit/fatigue/replay
//   body: { sequence_event_ids: string[] }
//   → { replayed: string[], irreversible: string[] }
//   对 sequence 内每条 audit_event 调对应的 inverse tool（D49 undoChain / D46 undoLastWrite / D44 inline reject）
//   chain_undo / write_undo = reversible；external_send / broadcast = irreversible
```

---

## 3. Data Flow

### 3.1 Inline Approval 拦截流程（cross-channel）

```
inbound message (wechat / telegram / CLI)
    ↓
    conversation-loop.ts: parse tool_call
    ↓
    InlineApprovalPolicy.evaluate(toolCall, auditLog, sensitivityRegistry)
    ↓
    switch decision.action:
      case 'allow':
        execute tool → audit_event{ decision: 'allow', fatigue_signal?: { count: <3, ... } }
      case 'cooldown':
        render "已批 N 个，建议稍等..." → sleep 3s (interrupted if owner /cancel) → re-evaluate
        ↓
        on proceed → audit_event{ fatigue_signal, cooldown_applied: { duration_ms: 3000 } }
      case 'checklist':
        render checklist prompt (per item: "我已读后果", "我确认目标") → owner 勾 N items → execute tool
        ↓
        on proceed → audit_event{ fatigue_signal, checklist_required: true }
    ↓
    audit_event 落 D63 audit_event 表 (correlation_id 透传)
```

### 3.2 跨 Channel 一致性

| Channel | 入口 | 共享组件 |
|---|---|---|
| wechat | `apps/api/src/wechat-inbound-butler.ts` (existing) | `lib/fatigue/policy.ts` |
| telegram | `apps/api/src/telegram-inbound-butler.ts` (existing) | 同 |
| CLI | `apps/api/src/cli-inline-approval.ts` (existing / new) | 同 |

每个 channel 在 `tryApprove` 入口前统一调 `evaluateInlineApproval` — 不在 channel handler 内重复实现 detection / cooldown / checklist 逻辑。

### 3.3 Replay Flow

```
owner: /v1/owner/audit/fatigue (GET)
    ↓
    scan D63 audit_event 表: 滑动 60s 窗口内 owner approve 序列
    ↓
    filter: count >= DEFAULT_COUNT_THRESHOLD
    ↓
    return sequences[] (sorted by start_ts DESC)

owner: POST /v1/owner/audit/fatigue/replay { sequence_event_ids }
    ↓
    load events by ids
    ↓
    for each event:
      switch event.tool_name:
        case 'write_file' / 'edit_file' / 'delete_file' → queue undoChain(D49) / undoLastWrite(D46)
        case 'run_command' → mark irreversible (D49 §4.6)
        case 'send_*' / 'broadcast_*' / 'external_write' → mark irreversible (sensitivity high — external side-effect)
    ↓
    execute reversible queue in reverse order
    ↓
    return { replayed: [event_id...], irreversible: [event_id...] }
```

**关键不变量**：
- replay 不修改 audit_event（不可变 — D63 lock）— 仅追加 `metadata.replayed_by: [event_id]`
- replay 一次只能 replay 一个 sequence（owner 主动确认）
- irreversible entry 不阻塞 sequence replay — 仅在 reply 列表说明

### 3.4 Reply 格式

```
[/v1/owner/audit/fatigue]
共发现 2 个连续 approve 序列（≥3/60s）：
1. 09:42:15 → 09:42:38 (3 个 approve): event-1, event-2, event-3
2. 09:51:02 → 09:51:45 (5 个 approve): event-7, event-8, event-9, event-10, event-11

回复 /replay <sequence_id> 重审
```

```
[/replay seq-1]
✅ event-1 (write_file apps/api/x.ts) → 已还原
✅ event-2 (edit_file apps/api/y.ts) → 已还原
❌ event-3 (send_email foo@bar.com) → 不可撤销（external side-effect）
```

3 列对齐 mobile readability（D48 §4.2 v7 baseline 已 ship）。

---

## 4. Error Handling

### 4.1 FatigueSignal 计算失败

| 场景 | 行为 |
|---|---|
| audit log DB 不可达 | signal.degraded=true + count=0 → decision 退化为 allow（保 owner 不被 lock out） |
| audit log 超时 (5s) | 同上 |
| window_seconds 非法 (≤0 / NaN) | throw Error "invalid window_seconds"（开发期捕获；prod 走 degrade 路径） |
| last_n_actions 截断 (>100) | 仅保留最近 100 条；audit_event.fatigue_signal.last_n_actions 标 truncated=true |

**设计原则**：degraded signal 永远降级为 allow — 不替 owner 决定（D48 §4.3 advice-not-action）。

### 4.2 Cooldown 被打断

| 场景 | 行为 |
|---|---|
| owner 发 /cancel during 3s wait | audit_event.cooldown_applied.interrupted=true → proceed |
| owner 发其他 command | 同 /cancel 处理 |
| 系统 timeout (e.g. ws 断) | audit_event.cooldown_applied.interrupted=true → 放弃当前 approve |

### 4.3 Checklist 超时 / 取消

| 场景 | 行为 |
|---|---|
| 60s 内未勾完 | default deny（保守） + audit_event.decision='deny' + reason='checklist_timeout' |
| owner 发 /cancel | 同 default deny + reason='checklist_cancelled' |
| 部分勾选 → 全部勾 → proceed | audit_event.checklist_required=true（记录曾拦截） |

### 4.4 /v1/owner/audit/fatigue 错误

| 场景 | 行为 |
|---|---|
| DB 不可达 | 200 + `{ sequences: [], degraded: true }`（不抛 5xx；response 顶层 degraded 字段标识） |
| sequence_event_ids 找不到 | 200 + `{ replayed: [], irreversible: [], missing: [event_id...] }` |
| replay 中途 undo 失败 | 200 + `{ replayed: [...], failed: [{ event_id, reason }] }`（已 undo 不回滚） |

### 4.5 Replay 安全边界

- 仅 replay owner 自己 actor 的 approve（cross-actor 防越权）
- 仅 replay 近 24h 内的 sequence（防 stale audit replay 干扰新 toolCalls）
- irreversible tool 不静默 — reply 列表必含 explanation

---

## 5. Testing

### 5.1 Unit (lib/fatigue)

**File**: `apps/api/src/lib/fatigue/signal.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **F1. 0 actions in window** | audit log empty | count=0, last_n_actions=[] |
| **F2. 3 actions in 60s** | 3 approve events at t=10,20,30 | count=3, last_n_actions.length=3 |
| **F3. window 边界** | events at t=10,20,80 (window=60) | count=2 (t=80 不在 60s 内) |
| **F4. degraded signal** | audit log reader throws | degraded=true, count=0 |
| **F5. truncated last_n_actions** | 150 events in window | last_n_actions.length=100, truncated=true |

**File**: `apps/api/src/lib/fatigue/policy.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **F6. allow low-signal normal tool** | signal.count=1, tool=read_file | action='allow' |
| **F7. cooldown high-signal normal tool** | signal.count=3, tool=read_file | action='cooldown', duration_ms=3000 |
| **F8. checklist high-sensitivity low-signal** | signal.count=0, tool=send_email | action='checklist', items.length=2 |
| **F9. cooldown → checklist (high-sensitivity high-signal)** | signal.count=3, tool=send_email | action='checklist'（先 cooldown 后 checklist，节省交互） |
| **F10. degraded signal always allow** | degraded=true, tool=send_email | action='allow'（不替 owner 决定） |

**File**: `apps/api/src/lib/fatigue/checklist.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **F11. match send_*** | tool_name='send_email' | level='high', items.length=2 |
| **F12. match delete_*** | tool_name='delete_file' | level='high' |
| **F13. no match read_file** | tool_name='read_file' | null（normal） |
| **F14. glob pattern coverage** | broadcast_telegram / external_write_patch | level='high' |

### 5.2 Integration (cross-channel)

**File**: `apps/api/src/lib/fatigue/cross-channel.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **X1. wechat high-signal send_email** | wechat inbound → 3 此前 approve → send_email | checklist 拦截 + 同一 audit_event shape |
| **X2. telegram high-signal delete_file** | telegram inbound → 3 此前 approve → delete_file | checklist 拦截 + 同一 audit_event shape |
| **X3. CLI high-signal normal tool** | CLI inbound → 3 此前 approve → read_file | cooldown 拦截 + 同一 audit_event shape |

### 5.3 API integration

**File**: `apps/api/src/lib/fatigue/replay-api.test.ts` (new)

| Case | 描述 | 断言 |
|---|---|---|
| **R1. GET empty** | audit log 没有连续序列 | sequences=[] |
| **R2. GET 2 sequences** | audit log 2 个独立序列 | sequences.length=2, sorted DESC by start_ts |
| **R3. POST replay mixed** | sequence 含 write + send_email | replayed=[write event], irreversible=[send_email event] |
| **R4. POST replay cross-actor reject** | sequence_event_ids 含其他 actor 的 event | 403 / replayed=[]（防越权） |

### 5.4 Acceptance scenarios (D52 harness +3)

**File**: `tests/acceptance/scenarios/_fixtures.ts` 新增 F1, F2, F3

| Scenario | 描述 |
|---|---|
| **F1-fatigue** | owner 在 60s 内连续 y 3 个 normal tool，第 4 个 flow 通过（cooldown 不真触发） | 4 approvals + 4 write_file 全部成功执行 |

> **Note (gap documented):** 接受 harness 通过 subagent audit log reader（`wechat-inbound-butler.ts:62-78` `subagentAuditAsFatigueReader`）读取疲劳信号，但 harness 不写 subagent events → `count=0` → fatigue 返回 `allow`。F1 是 flow smoke test，验证 4 approvals + 4 write_file 工具调用成功。**Cooldown 触发逻辑 + audit_event shape 在 unit + integration 层验证**：
> - Unit: `policy.test.ts` F7（high-signal normal tool → cooldown `duration_ms=3000`）
> - Integration: `cross-channel.test.ts` X1/X2/X3（cooldown path with mocked reader）
>
> 真 cooldown 验证在 acceptance 层需要 D65+：`audit_events` table 加 `listRecentAuditEvents` read method 后，subagent log reader 替换 + harness 支持写 audit events。 |
| **F2-sensitive** | owner 触发 send_email → checklist prompt → owner 勾完 → proceed → audit_event.checklist_required=true |
| **F3-replay** | owner 触发 4 个连续 approve → GET /v1/owner/audit/fatigue 返回 1 个 sequence → owner POST replay → reversible 已 undo, irreversible 在 reply 列表说明 |

### 5.5 不破现有 regression

- D44 inline-approval y/👌 路径全跑过（product lock — 1 token 通过）
- D46 UNDO_STACK + D49 UNDO_CHAIN 不动（mechanism lock）
- D63 audit_event schema 不动 correlation_id（仅加 optional fatigue_signal）
- 现有 41/41 realistic scenarios 全跑过
- 现有 1957/1/0 test baseline 不退化

### 5.6 验收指标

- 全 new tests pass (14 unit + 3 integration + 4 API + 3 acceptance = ~24 new)
- 全 41/41 realistic pass (no regression) → 期望 44/44
- 全 test baseline +24 new pass
- 0 lint error
- 0 LLM call (纯 mechanism，纯逻辑层)

---

## 6. Files Changed (预估)

| 类型 | 路径 | 改动 |
|---|---|---|
| 新 | `apps/api/src/lib/fatigue/signal.ts` | computeFatigueSignal + DEFAULT_* |
| 新 | `apps/api/src/lib/fatigue/policy.ts` | evaluateInlineApproval + DEFAULT_COOLDOWN_MS |
| 新 | `apps/api/src/lib/fatigue/checklist.ts` | matchSensitivity + HIGH_SENSITIVITY_TOOLS + DEFAULT_CHECKLIST_ITEMS |
| 新 | `apps/api/src/lib/fatigue/audit-event.ts` | AuditEventFatigue 扩展 type |
| 新 | `apps/api/src/lib/fatigue/replay.ts` | /v1/owner/audit/fatigue handler |
| 改 | `apps/api/src/wechat-inbound-butler.ts` | 入口调 evaluateInlineApproval (existing) |
| 改 | `apps/api/src/telegram-inbound-butler.ts` | 同 |
| 改 | `apps/api/src/cli-inline-approval.ts` | 同 |
| 改 | `apps/api/src/audit-event.ts` | +fatigue_signal / +cooldown_applied / +checklist_required 字段 (optional) |
| 新 | `apps/api/src/lib/fatigue/signal.test.ts` | 5 unit |
| 新 | `apps/api/src/lib/fatigue/policy.test.ts` | 5 unit |
| 新 | `apps/api/src/lib/fatigue/checklist.test.ts` | 4 unit |
| 新 | `apps/api/src/lib/fatigue/cross-channel.test.ts` | 3 integration |
| 新 | `apps/api/src/lib/fatigue/replay-api.test.ts` | 4 API |
| 改 | `tests/acceptance/scenarios/_fixtures.ts` | +F1-fatigue +F2-sensitive +F3-replay scenarios |

预估 +500/-30 行；0 业务逻辑改动到现有 inline-approval / UNDO_CHAIN / audit_event correlation_id 路径。

---

## 7. v5 DESIGN alignment

- §7.1 Ports: 不引入新 Port（仅扩 audit-event metadata + inline-approval policy 层）
- §10.4 Sandbox: 不影响 sandbox；cooldown sleep 在 butler-v5 process 内
- §11.3 Approval: inline-approval 决策前移（仍 1 token 通过，但前置 cooldown/checklist 拦截）
- §12 Knowledge: 不涉及 durable memory / candidate
- §18 Trigger guard: 撞点驱动（D48 §3.1 owner 实测）— 不适用 §18 row 3 延后协议

---

## 8. D64 Ship Cycle（沿用 D55-D63 协议, 10th cycle）

| Track | 内容 | Commit |
|---|---|---|
| **T1** | signal + policy + checklist (lib/fatigue/{signal,policy,checklist}.ts + tests) | T1 commit |
| **T2** | audit_event schema 扩展 (audit-event.ts +3 optional fields + correlation_id 不动) | T2 commit |
| **T3** | cross-channel 接入 (wechat + telegram + CLI 共享 evaluateInlineApproval) | T3 commit |
| **T4** | /v1/owner/audit/fatigue replay API | T4 commit |
| **T5** | acceptance scenarios (F1-fatigue + F2-sensitive + F3-replay) | T5 commit |
| **post-fix** | drift closure (D50 protocol — fresh N=3 verify, 不信 last batch) | post-fix commit |

预期 6 commits（D55-D63 cycle 形态），push-to-main 默认（D62 D63 同模式）。

---

## 9. Lessons / 注意事项

- **D44 ergonomics lock**：y/👌 仍 1 token 通过；cooldown/checklist 在 y 之前拦截，不破坏产品力
- **D63 schema lock**：audit_event.correlation_id 不动；fatigue_signal 作为 optional 字段（backward-compatible）
- **D49 UNDO_CHAIN lock**：replay 调用 D49 undoChain / D46 undoLastWrite，不重新实现 undo 逻辑
- **degraded fail-safe allow**：不替 owner 决定（D48 §4.3 advice-not-action），但 lock-out 风险更低
- **owner-tunable 推迟到 D65+**：v1 硬编码阈值；后续如需 owner 调（per project / per channel）再扩
- **cross-channel 不留例外**：wechat / telegram / CLI 同一 policy；不在 CLI 留"fast-path"绕过

---

## 10. Acceptance Gates (N=3 fresh verify)

- lint 0 / typecheck 0 / test:full +24 new / acceptance 41→44+
- raw findings 存盘 `.audit/D64/` (D57 lesson #1 protocol)
- audit_event shape 含 fatigue_signal 字段（D63 schema 兼容验证）
- cross-channel fixture 跑出同一 audit_event shape（X1/X2/X3 integration 通过）

---

**End D64 design doc.**
