# P2 Batch — 「撤销 空承诺」+「长消息 spam」设计 spec

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-08-v5-p2-batch.md`（plan 阶段产出）。
> **背景**：D44 (`854c16ee..6b40d69d`) 已 ship 4 项产品层修复（inline-approval intent / read-only argv bypass / usage 埋点 / pre-commit sync）。35 realistic scenarios (commit `aadf23ce`) 产品层 gap 分析识别 6 项 gap，其中 P0/P1 已 ship（69dc924c + 46ef4db3），**P2 剩 2 项未修**：
> - 「撤销 空承诺」：owner 说中文自然语言 "撤销刚才"（无 `/undo` 前缀）走 LLM 路径，可能返回 "好的已撤销" 空承诺；`/undo` 无 path 时盲目 pop workspaceRoot 返 "无 ... 的撤销记录"
> - 「长消息 spam」：现有 `detectSpam` 3 标志（>2000 chars / 单 char 重复 > 30 + ≥ 30% / emoji 占比 > 60%）漏多种 spam pattern — per-line 重复 / whitespace-token 重复 / 1500-2000 合法结构中文
>
> **优先级**：仅 P2 这两块；其它 6 项 gap 中 4 项已 ship，剩 0 项。
> **影响面**：`apps/api/src/wechat-undo-command.ts`（改 startsWith + fallback）；`apps/api/src/wechat-inbound-butler.ts`（扩 detectSpam）；`tests/acceptance/product-regressions.test.ts`（追加 8 case）。**0 架构边界动** — §3 6 硬规则 + §20 16 invariant 保持。

---

## 1. 目标

解决 owner 撞的 P2 阶段两个真实产品层痛点：

1. **中文自然语言路由** — owner 说 "撤销刚才" / "撤销上一步" / "撤销"（无 `/undo` 前缀）能被 `tryWechatUndoCommand` 接住，不走 LLM（避免 "好的已撤销" 空承诺）
2. **`/undo` 无 path graceful fallback** — 不再盲目 pop workspaceRoot（总是空）；返 "请用 `/undo <path>`"
3. **多信号 spam 护栏（3 新标志）** — `detectSpam` 在现有 3 标志后追加 per-line / whitespace-token / length+structure 3 flag；mock harness 锁 3 case
4. **0 LLM variance 路径** — 全部 pre-LLM 确定性判定；mock harness fixture marker `SHOULD_NOT_BE_USED` 防 LLM 兜底
5. **0 架构边界动** — 不改 §3 依赖方向 / §20 invariant / §10 治理 / §6 application orchestrator
6. **0 first-class event 新增** — 走现有 `traces: ["spam-guard: ..."]` / 命令 reply（与 46ef4db3 同模式）

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| 「撤销」路由位置 | **扩 tryWechatUndoCommand** (vs 新建独立 gate) — 复用现有 pop 逻辑；yagni |
| 中文 intent patterns | `^(撤销\|撤销刚才\|撤销上一步\|撤销上次\|撤销上一次\|undo\|/undo\|/撤销)\s*$` (case-insensitive) |
| `/undo` 无 path fallback | **直接返 "请用 `/undo <path>`"**，不再试 workspaceRoot（与 46ef4db3 broken 路径对齐消除） |
| Spam 新 flag 数量 | **3 标志**（per-line / whitespace-token / length+structure）— 用户选 "多信号 spam 护栏" |
| Per-line 阈值 | lines ≥ 10 + unique_ratio < 0.3 |
| Whitespace-token 阈值 | tokens ≥ 10 + max_count > 20 + ratio ≥ 0.3 |
| Length+structure 范围 | 1500 < len ≤ 2000 + 无换行 + 标点占比 < 0.5% |
| Flag 优先级 | 现有 3 标志 → 新 3 标志（顺序按"危害度"，短字符重复先于长结构） |
| 失败处理 | detectSpam fail-open 不变（仅 return null 时走 LLM） |
| Schema | 0 变化 |
| First-class event | 0 新增 |
| Arch guard | 0 新增（pure fn 在现有文件中扩，不动 domain 边界） |
| Mock harness | 追加 8 case 到 `product-regressions.test.ts`（F1 两态 / F2 / F3 / F4 / F5 / + 2 回归锁） |

---

## 3. 现状与不一致

### 3.1 已 ship（46ef4db3 + b8d5f28a + cc0f736d）

- 46ef4db3 P1+P2 closure：capability.executed audit + `/undo <path>` + `detectSpam` 3 标志
- b8d5f28a `product-regressions.test.ts` L49-93：lock `/undo` 真实审批 + 还原
- b8d5f28a `product-regressions.test.ts` L95-114：lock `"请".repeat(80)` 单字符重复
- cc0f736d `product-regressions.test.ts`：clarify spam guard regression 注释
- `tryWechatUndoCommand` 已含 `/undo` + `/撤销` 路由；`undoLastWrite` + UNDO_STACK + workspace-tools
- `detectSpam` 在 `wechat-inbound-butler.ts:531-566` 有 3 标志（`MAX_SPAM_CHARS` / `REPEAT_TOKEN_THRESHOLD` / `EMOJI_RATIO_MAX`）

### 3.2 真缺（2 gap）

- **Gap 1（撤销 空承诺）**：中文自然语言 "撤销刚才" 不被任何命令拦截；走 LLM 路径，fixture 不控制真实 LLM 行为；`/undo` 无 path 时 fallback 走 `undoLastWrite(workspaceRoot, ".")` 永远返 "无 ... 的撤销记录"（workspaceRoot 不在 UNDO_STACK 中）
- **Gap 2（长消息 spam 多信号）**：3 现有标志漏 3 类（每类 example 经实测会触发现有 flag 故需 token / line / structure 维度）：
  - (a) Per-line 重复：多行多字行重复（如 `"hello\n".repeat(40)` = 240 chars, 40 行；char counts 平衡 maxCount=40 ratio=0.17 不命中现有 char repeat）—— 现有按 char 频次无法识别"行级重复"
  - (b) Whitespace-token 重复：英文 multi-word token 重复（如 `"hello world ".repeat(40)` = 480 chars, 80 tokens；maxCount=40 ratio=0.083 不命中现有 char repeat ratio 阈值）—— 现有按 char 频次无法识别 token 级重复
  - (c) Length+structure：1500-2000 字符多字符合法结构中文（无标点无换行）—— 现有 > 2000 才拦，1500-2000 区间漏；现有 char repeat 阈值 30 也不命中（高度变化的字符）

### 3.3 文档 drift

- 无 doc drift；本 spec 实施后：
  - §13 风险与自治：0 触（undo 失败仍按 46ef4db3 模式返 honest reply）
  - §14 observability：0 新 first-class event
  - §11 / §18：0 触（不属 trigger-conditioned 设计）

### 3.4 Persistence 缺口

- 无 persistence 缺口；UNDO_STACK + `undoLastWrite` 已存在，仅 caller-side routing/fallback 改动

---

## 4. 设计

### 4.1 「撤销 空承诺」修法（1 文件）

`butler-v5/apps/api/src/wechat-undo-command.ts`：

```typescript
/**
 * /undo command — revert last write_file per absolute path (P2 batch v2 2026-09-08).
 *
 * Routes content matching `/undo` / `/撤销` / 中文自然语言 (撤销/撤销刚才/
 * 撤销上一步/撤销上次/撤销上一次/undo) here. Without a path argument,
 * returns a graceful "请用 `/undo <path>`" reply rather than blindly probing
 * the workspace root.
 *
 * Usage: `/undo <path>` to revert the most recent write_file to that path.
 * Without a path argument, owner should retry with explicit path.
 */
import { writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { mkdirSync } from "node:fs"
import { undoLastWrite, pendingUndoCount } from "./workspace-tools.js"
import type { ButlerLoopResult } from "./wechat-inbound-butler.js"
import type { Wiring } from "./wiring.js"

const UNDO_INTENT_REGEX =
  /^(撤销|撤销刚才|撤销上一步|撤销上次|撤销上一次|undo|\/undo|\/撤销)\s*$/i

function done(reply: string, traces: readonly string[] = []): ButlerLoopResult {
  return { reply, iterations: 0, toolCalls: 0, finalDecision: "Respond", traces: [...traces] }
}

export async function tryWechatUndoCommand(args: {
  readonly wiring: Wiring
  readonly fromUserId: string
  readonly content: string
  readonly env?: NodeJS.ProcessEnv
}): Promise<ButlerLoopResult | null> {
  const env = args.env ?? process.env
  const trimmed = args.content.trim()
  if (!UNDO_INTENT_REGEX.test(trimmed)) {
    return null  // 不匹配 → 走 LLM 路径（保留原行为）
  }

  const workspaceRoot = (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
  const rest = trimmed.replace(UNDO_INTENT_REGEX, "").trim()

  // F2: 无 path → graceful fallback（不再盲目 pop workspaceRoot）
  if (rest.length === 0) {
    return done("请用 `/undo <path>` 指定要还原的文件路径。")
  }

  // 显式 path：pop + restore（或 delete if was new）
  const beforeContent = undoLastWrite(workspaceRoot, rest)
  if (beforeContent === undefined) {
    return done(`无 ${rest} 的撤销记录（栈中无内容或已用完）`)
  }
  const resolved = resolve(workspaceRoot, rest)
  try {
    if (beforeContent === null) {
      // 新建文件：置空（与 46ef4db3 行为一致）
      writeFileSync(resolved, "", "utf8")
      return done(`[undo] ${rest} 是新建文件，已置空（如需彻底删除请手工 rm）`)
    }
    mkdirSync(dirname(resolved), { recursive: true })
    writeFileSync(resolved, beforeContent, "utf8")
    return done(`[undo] ${rest} 已还原为上版内容（栈余 ${pendingUndoCount(workspaceRoot, rest)}）`)
  } catch (err) {
    return done(`[undo] 失败：${err instanceof Error ? err.message : String(err)}`)
  }
}
```

**架构不变量遵守**：
- §20 #2: 不 import 具体 adapter（仅 undoLastWrite + writeFileSync）
- §3 #4: Governance SDK-isolated — 不调 policy / grant / approver
- §13 风险与自治: undo 失败返 honest reply，不静默吞错

**回滚**：原 `startsWith("/undo")` / `startsWith("/撤销")` + 无 path 盲目 pop workspaceRoot 路径删除（已被新 regex + graceful fallback 替代）。**无外部依赖删除**——UNDO_STACK / workspace-tools 不动。

### 4.2 「长消息 spam」多信号护栏（1 文件）

`butler-v5/apps/api/src/wechat-inbound-butler.ts` → `detectSpam()`：

```typescript
const MAX_SPAM_CHARS = 2000
const REPEAT_TOKEN_THRESHOLD = 30
const EMOJI_RATIO_MAX = 0.6

// P2 batch v2 (2026-09-08): 多信号 spam 护栏
const MIN_LINE_REPEAT_TOTAL = 10
const LINE_REPEAT_RATIO_MAX = 0.3  // unique_lines / total_lines

const MIN_TOKEN_REPEAT_TOTAL = 10
const TOKEN_REPEAT_THRESHOLD = 20
const TOKEN_REPEAT_RATIO_MAX = 0.3

const STRUCTURE_MIN_LEN = 1500
const STRUCTURE_MAX_LEN = 2000  // > 2000 已被 MAX_SPAM_CHARS 拦
const STRUCTURE_PUNCT_RATIO_MAX = 0.005  // < 0.5%
const STRUCTURE_PUNCT_REGEX = /[。，！？；：、,.!?;:]/

/**
 * Cheap heuristic spam detection before invoking the LLM. Returns a short
 * user-facing reply when the input is suspicious, or null when it looks
 * normal. False positives are acceptable: the owner can re-send a concrete
 * request. False negatives are acceptable too: LLM still has the existing
 * fixture-exhausted / decode-fail safety nets downstream.
 */
function detectSpam(content: string): string | null {
  if (content.length === 0) return null

  // F-现有: 总长超限
  if (content.length > MAX_SPAM_CHARS) {
    return `消息过长（${content.length} 字符，上限 ${MAX_SPAM_CHARS}）。请发具体需求。`
  }

  // F-现有: 单字符重复（CJK 内容无 whitespace，按 char 频次）
  if (content.length >= 50) {
    const charCounts = new Map<string, number>()
    for (const ch of content) charCounts.set(ch, (charCounts.get(ch) ?? 0) + 1)
    let maxChar = ""
    let maxCount = 0
    for (const [c, n] of charCounts) {
      if (n > maxCount) { maxCount = n; maxChar = c }
    }
    if (maxCount > REPEAT_TOKEN_THRESHOLD && maxCount / content.length >= 0.3) {
      return `检测到字符「${maxChar}」重复 ${maxCount} 次。请发具体需求。`
    }
  }

  // F-现有: Emoji 占比
  let emojiCount = 0
  for (const ch of content) {
    const code = ch.codePointAt(0) ?? 0
    if (code >= 0x1f000 && code <= 0x1ffff) emojiCount += 1
  }
  if (content.length >= 20 && emojiCount / content.length > EMOJI_RATIO_MAX) {
    return `检测到 emoji 占比 ${Math.round((emojiCount / content.length) * 100)}%。请发具体需求。`
  }

  // F3: Per-line 重复（多行短行重复）
  if (content.length >= 100) {
    const lines = content.split(/\r?\n/).filter((l) => l.length > 0)
    if (lines.length >= MIN_LINE_REPEAT_TOTAL) {
      const unique = new Set(lines)
      if (unique.size / lines.length < LINE_REPEAT_RATIO_MAX) {
        return `检测到 ${lines.length} 行中只有 ${unique.size} 种，疑似重复内容。请发具体需求。`
      }
    }
  }

  // F4: Whitespace-token 重复（多字 token 间空格重复）
  if (content.length >= 50) {
    const tokens = content.split(/\s+/).filter((t) => t.length > 0)
    if (tokens.length >= MIN_TOKEN_REPEAT_TOTAL) {
      const counts = new Map<string, number>()
      for (const t of tokens) counts.set(t, (counts.get(t) ?? 0) + 1)
      let maxToken = ""
      let maxCount = 0
      for (const [t, n] of counts) {
        if (n > maxCount) { maxCount = n; maxToken = t }
      }
      if (maxCount > TOKEN_REPEAT_THRESHOLD && maxCount / tokens.length >= TOKEN_REPEAT_RATIO_MAX) {
        const display = maxToken.length > 20 ? `${maxToken.slice(0, 20)}...` : maxToken
        return `检测到 token「${display}」重复 ${maxCount} 次。请发具体需求。`
      }
    }
  }

  // F5: Length+structure（1500-2000 字符无标点无换行）
  if (content.length > STRUCTURE_MIN_LEN && content.length <= STRUCTURE_MAX_LEN) {
    const hasNewline = content.includes("\n")
    let punctCount = 0
    for (const ch of content) if (STRUCTURE_PUNCT_REGEX.test(ch)) punctCount += 1
    if (!hasNewline && punctCount / content.length < STRUCTURE_PUNCT_RATIO_MAX) {
      return `消息结构异常（${content.length} 字符无标点无换行）。请分批发送或简化需求。`
    }
  }

  return null
}
```

**架构不变量遵守**：
- §3 #4: 纯函数（除 env/global 不依赖任何 adapter；仅 string 操作）
- §13 风险与自治: 失败仍返 null 走 LLM（与 46ef4db3 一致）
- §14 observability: 0 新 first-class event

**回滚**：3 现有 flag 不变；3 新 flag 在末尾追加；失败/边界处理同模式（return null skip）。

### 4.3 测试策略（8 fixture case）

追加到 `butler-v5/tests/acceptance/product-regressions.test.ts`：

| Suite | Case | Input | Reply pattern | toolCalls | finalDecision |
|-------|------|-------|---------------|-----------|---------------|
| F1-A | 「撤销」无 undoable op | `撤销刚才`（无前置 write_file） | `/没有可撤销\|指定.*路径/` | 0 | Respond |
| F1-B | 「撤销」有 undoable op | 1. write_file→审批→确认；2. `撤销刚才` | `/已还原/` | 0 | Respond |
| F2 | `/undo` 无 path | `/undo`（无前置） | `/指定.*路径/` | 0 | Respond |
| F3 | Per-line 重复（多字行） | `"hello\n".repeat(40)` = 240 chars 40 行 | `/行.*种\|重复内容/` | 0 | Respond |
| F4 | Whitespace-token 重复（英文） | `"hello world ".repeat(40)` = 480 chars 80 tokens | `/token\|重复.*次/` | 0 | Respond |
| F5 | Length+structure（合法中文） | 1750 chars 多样化 CJK（每 char < 30 次），无标点无换行 | `/结构异常\|无标点/` | 0 | Respond |
| 回归 A | C4 单字符重复 | `"请".repeat(80)` | `/字符「请」重复/` | 0 | Respond |
| 回归 B | `/undo <path>` 全流程 | 同 b8d5f28a L49-93 | `/已还原/` | 0 | Respond |

每个 case 独立 conversationId；fixture marker `SHOULD_NOT_BE_USED` 防 LLM 兜底（除 F1-B + 回归 B 必须真走完审批）。

### 4.4 边界遵守（DESIGN §段）

- §3 6 硬规则 (D33 lock): 0 触（pure fn 扩；不 import adapter）
- §20 16 invariant (D26A + D26B): 0 触
- §12 G1-G5 (D39-D43 ship): 0 触（与 memory 层无关）
- §13 风险与自治: 0 触（undo 失败返 honest reply）
- §14 observability: 0 新 first-class event
- §10 Governance (D27 ship): 0 触（不走 policy / grant / approver）
- §11 / §18 trigger-conditioned: 0 触（本批不属 trigger 设计）

---

## 5. 文件 ops 清单（预估 ~5 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `apps/api/src/wechat-undo-command.ts` | +25/-15 | 改 startsWith → UNDO_INTENT_REGEX；删 `/u(ndo)?` 拆分；无 path fallback 改 graceful |
| `apps/api/src/wechat-inbound-butler.ts` | +50/-0 | detectSpam 追加 F3/F4/F5 3 if-block |
| `tests/acceptance/product-regressions.test.ts` | +180/-0 | 追加 8 fixture case（独立 conversationId） |
| `docs/superpowers/specs/2026-09-08-v5-p2-batch-design.md` (this) | +400/-0 | spec |
| `docs/superpowers/plans/2026-09-08-v5-p2-batch.md` | +300/-0 | plan (plan 阶段产出) |

总预估: ~5 file ops / +955 prod+test+doc

---

## 6. 不做（明确范围外）

- **撤销 pending approval**: scope 限文件 undo；approval cancel 路径属 §18 trigger 体系，本批不动
- **LLM 路径理解**: mock harness 不能锁 LLM；本批纯 pre-LLM
- **Cross-process undo stack persistence**: 保留 per-process only（46ef4db3 决策）
- **embedding-based spam detection**: §12 line 593 + D30 case #6 lock 默认不启用 embedding；本批纯字符串
- **sliding window repetition detector**: overkill；多信号 3 标志已够覆盖 35 scenarios 实证 gap
- **Owner UI for dedup/spam feedback**: 本批仅 short reply；UI 后续
- **New Core Port (UndoPort / SpamGuardPort)**: 与 Channel Port 类比；待 §7 audit 触发；本批不动
- **降低现有 3 标志阈值**: 不解决新维度 case；保留 46ef4db3 阈值
- **Cron / schedule cleanup**: spam 是 pre-LLM check，无 leftover；本批不动
- **Auto-promote / auto-merge**: 与 dedup 同因，违反 §12 line 600 不建设

---

## 7. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-08-v5-p2-batch.md`（plan 阶段产出）
2. **实施**: 改 wechat-undo-command.ts (F1+F2) + 扩 wechat-inbound-butler.ts detectSpam (F3+F4+F5) + 追加 product-regressions.test.ts 8 case
3. **验证**: typecheck + lint（每 commit 后跑）+ product-regressions.test.ts 8 case 全绿 + 全量 vitest 不回归
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D46-section12-p2-batch-2026-09-08.md`（仿 D44 / D45 格式）
5. **commit**: `feat(product): P2 batch — 撤销空承诺 + 多信号 spam 护栏`
6. **Handoff**: `.blackboard/shifts/2026-09-08-p2-batch-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D47+: LLM 真实输出质量量化（v8 PRD candidate C：fixture-recording）
   - D48+: Owner 实测 1 周后的视角笔记（v8 candidate D）

---

## 8. 关联

- D44 product-layer-followups — `memory/project-fix-D44-product-layer-followups-2026-09-08.md`
- D45 engineering-hygiene — `memory/project-fix-D45-engineering-hygiene-2026-09-08.md`
- 46ef4db3 feat(usage+undo+spam): capability telemetry + /undo command + spam guard (P1+P2 closure) — `memory/project-product-realistic-scenarios-2026-09-04.md`
- 35 realistic scenarios 产品层分析 — `butler-v5/tests/acceptance/scenarios/_analyze.md` + `realistic.test.ts`
- acceptance harness 基础 — `butler-v5/tests/acceptance/harness.ts` + `memory/project-feature-acceptance-harness-2026-09-04.md`
- 6 product gap 候选 — `memory/MEMORY.md` (Post-D43 Sessions 段)
- §3 6 硬规则 (D33 lock) — `memory/project-fix-D33-section3-dependency-2026-08-31.md`
- §20 16 invariant (D26A + D26B) — `memory/project-fix-D26A-section20-batch-A-2026-08-31.md` + `memory/project-fix-D26B-section20-batch-B-2026-08-31.md`
- V8 PRD shell — `docs/superpowers/plans/v5-real-llm-v8-iteration-2026-09.md`（候选 D: owner hand-trial 触发）

---

**Spec version**: v1 (brainstorming closed 2026-09-08)
**Spec status**: awaiting user review
