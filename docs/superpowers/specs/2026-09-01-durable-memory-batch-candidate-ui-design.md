# Durable Memory Batch Candidate UI — 设计 spec

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-01-durable-memory-batch-candidate-ui.md`（plan 阶段产出）。
> **背景**：DESIGN §18 line 653-668 第 3 行 "Durable Memory / Project Knowledge 表" 触发条件 "真实召回/资料管理需求 + Transcript 不够" 仍标 "未触发"；§11 line 438 第 5 行 `memory_records` pgTable 同样标 "未触发"。但 D30 §12 audit lock 6 cases + R10 handoff "Durable Memory MVP 已落地" + 实际 recall_durable_memory/recall_document/recall_project_knowledge 3 个工具 + wechat `/记住 /记忆 /确认记忆` 3 命令 + owner routes confirm/reject/delete + durable-memory-inject opt-in 工作集注入 + project-knowledge-sync K1 sources manifest — **MVP 主体已 ship**。本 spec (a) 承认 MVP 状态、改 §18/§11 行状态 note 与 port-catalog.md 同步；(b) 补 owner 实际撞的 G3 batch candidate UI（一组 confirm/reject 只能 1 个，candidate 多到处理不动）。
> **优先级**：§18 trigger 撤销 (G0) + G3 batch candidate UI；其余 G1 expires cleanup / G2 dedup / G4 auto-promote / G5 跨 project PK recall 推到下轮。G6 model-side ingest_document 不做（§12 line 599 "默认不建设 auto-index"）。
> **影响面**：`packages/persistence` 加 `countBySubject` + `listBySubject.offset` 2 个能力；`apps/api` 加 3 个 owner routes + 1 个 wechat 新命令 + `/确认记忆` 扩面；DESIGN §12 audit state + port-catalog §3 加 1 行；D16 §18 arch guard case 视情况撤销。D22 §11 memory_records 行无需改（已确认走 §12 durable_memories 路径）。

---

## 1. 目标

把 §18 trigger row 3 从 "未触发（schema/MVP 在跑，缺工具面）" 收敛为 "已 MVP ship（schema + recall + 注入）+ 部分生命周期（G3 batch UI）"，同时记录剩余 5 个 G 留待下轮：

1. **状态承认（G0）**：DESIGN §18 row 3 + §11 row 5 status note + port-catalog.md §3 加 MemoryService 待物化行；与 §12 D30 lock + R10 handoff 描述对齐
2. **D16 arch guard 调整**：D16 `tests/architecture/section18-trigger-guard.test.ts` 中涉及 Durable Memory 的 case 由 "0 invoke" 改为 "MVP ship" 类（具体 case 由 plan 阶段检索）
3. **G3 batch candidate UI**：owner routes 加 3 路由（GET list / POST confirm-batch / POST reject-batch）+ wechat 加 `/记忆候选` 命令 + `/确认记忆` 支持 batch ids
4. **Persistence 最小扩展**：durable-memory-store 加 `offset` 到 `listBySubject` + 新 `countBySubject({subject, status?})` 方法
5. **不触 §11.4 不默认建设**：0 broker / bus / worker；0 新 Core Port

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| Scope | (a) G0 doc drift + (b) G3 batch candidate UI |
| Batch 上限 | 50 ids / batch（owner-routes）；20 ids / wechat command 单次 |
| Subject mismatch | 进 `failed[]` 而非 403（partial-failure 语义，便于调试） |
| Route vs Domain batching | route-layer sequential（for-of）；不动 domain 接口 |
| Persistence 扩展 | 加 `listBySubject.offset` + 新 `countBySubject` 方法（2 能力） |
| First-class event | 0 新增；沿用现有 `memory_confirm` / `memory_reject` per-id emit path |
| Port 物化 | 0 物化新 Core Port；MemoryService 在 port-catalog.md §3 待物化行加 1 条 |
| 推下轮 | G1 expires cleanup / G2 dedup / G4 auto-promote / G5 跨 project PK recall / G6 model ingest_document |

---

## 3. 现状与不一致

### 3.1 已 ship（MVP）

| 能力 | 位置 | 状态 |
|------|------|------|
| `recall_durable_memory` tool | `apps/api/src/tools.ts:444-454` + impl 597 | ✅ substring 检索 |
| `recall_document` tool | `apps/api/src/tools.ts:456-466` + impl 642 | ✅ plaintext/markdown/pdf-extracted-text |
| `recall_project_knowledge` tool | `apps/api/src/tools.ts:468-482` + impl 682 | ✅ per-project |
| Durable Memory schema 4 字段 + 3 sourceKind | `packages/domain/src/knowledge/durable-memory.ts:19-32` + D30 lock | ✅ |
| Durable Memory confirm/reject 单 record 纯函数 | `durable-memory.ts:154-177` | ✅ |
| `createDurableMemoryStore` | `packages/persistence/src/durable-memory-store.ts:43` | ✅ create/get/update/delete/listBySubject/deleteBySource* |
| Owner routes 单 record | `apps/api/src/owner-routes.ts:278-371` | ✅ POST + confirm + reject + DELETE |
| Wechat `/记住 /记忆 /确认记忆` | `apps/api/src/wechat-memory-commands.ts:23-99` | ✅ |
| Working-set inject (Durable Memory) | `apps/api/src/durable-memory-inject.ts` opt-in via `BUTLER_V5_DURABLE_MEMORY` | ✅ |
| Project Knowledge schema 4 kinds + D30 lock | `packages/domain/src/knowledge/project-knowledge.ts:32-42` | ✅ |
| Project Knowledge owner routes CRUD + sync + promote-* | `owner-routes.ts:488-630` | ✅ |
| K1 sources manifest sync (markitdown MCP) | `apps/api/src/project-knowledge-sync.ts` | ✅ |
| Working-set inject (Project Knowledge) | `apps/api/src/project-knowledge-inject.ts` opt-in via `BUTLER_V5_PROJECT_KNOWLEDGE` | ✅ |
| Wechat project surface | `apps/api/src/wechat-project-surface.ts` | ✅ |
| §12 D30 lock 6 cases | `tests/architecture/section12-knowledge-memory.test.ts` | ✅ |

### 3.2 真缺（5 gap）

| Gap | 状态 |
|---|---|
| **G1** expires cleanup job | expiresAt 字段 + isActive filter 已 ship；0 cron / schedule / prune 调用 |
| **G2** dedup similar candidates | 0 invoke（grep "dedup" 仅在 `ilink-poller.ts:145` 不在 durable-memory） |
| **G3** batch candidate UI | `/确认记忆` 仅最近 1 个（`wechat-memory-commands.ts:87` `candidates.at(-1)`）；无 batch owner route |
| **G4** Layer 1→2 auto-promote | 模型无自动从 Message 提炼 candidate 路径；只有 owner `/记住` + document promote 命令 |
| **G5** 跨 project PK recall | `recall_project_knowledge` 仅当前 projectId（`tools.ts:478-479`） |
| **G6** model-side ingest_document | owner route 需 pre-extracted text；pdf 需外部 markitdown；与 §12 line 599 "默认不建设 auto-index" 冲突 → 不做 |

### 3.3 文档 drift（3 处）

| Drift | 位置 | 应改 |
|---|---|---|
| §18 row 3 status "未触发" | DESIGN §18 line 656 | "已 MVP ship，缺 G1-G5 生命周期" |
| §11 row 5 status "未触发" | DESIGN §11 line 438 | "走 §12 durable_memories 路径满足 MVP；独立 memory_records 表待 §18 row 3 G3+ 触发" |
| port-catalog.md §3 缺 MemoryService 行 | port-catalog.md §3 | 加 "MemoryService — 待物化为 Core Port；MVP 直调 persistence（与 Channel Port 类比）" |

### 3.4 Persistence 缺口

| 缺口 | 位置 | 应改 |
|---|---|---|
| `listBySubject` 无 offset | `durable-memory-store.ts:16-20` | 加 `readonly offset?: number` |
| 无 `countBySubject` 方法 | 同上 | 新增 `readonly countBySubject: (input: {subject, status?}) => Promise<number>` |

---

## 4. 设计

### 4.1 Persistence 扩展（1 文件 + 1 test）

`packages/persistence/src/durable-memory-store.ts`:

```typescript
export interface DurableMemoryStore {
  // ... existing ...
  readonly listBySubject: (input: {
    readonly subject: string
    readonly status?: DurableMemoryStatus
    readonly limit?: number
    readonly offset?: number  // NEW
  }) => Promise<readonly DurableMemoryRecord[]>
  readonly countBySubject: (input: {  // NEW
    readonly subject: string
    readonly status?: DurableMemoryStatus
  }) => Promise<number>
}

export function createDurableMemoryStore(db: ButlerDb): DurableMemoryStore {
  // ... existing ...

  async listBySubject(input) {
    const limit = input.limit ?? 50
    const offset = input.offset ?? 0
    // add .offset(offset) to both branches (status filter / no filter)
    // existing 2 branches; offset default 0 = backward compatible
  },

  async countBySubject(input) {
    const rows = input.status
      ? await db
          .select({ count: sql<number>`count(*)::int` })
          .from(durableMemories)
          .where(
            and(
              eq(durableMemories.subject, input.subject),
              eq(durableMemories.status, input.status),
            ),
          )
      : await db
          .select({ count: sql<number>`count(*)::int` })
          .from(durableMemories)
          .where(eq(durableMemories.subject, input.subject))
    return rows[0]?.count ?? 0
  },
  // ...
}
```

`packages/persistence/src/durable-memory-store.test.ts` 加 4 cases:
- `listBySubject({offset: 5})` 跳过前 5 条
- `listBySubject({offset: 0})` 行为不变（regression）
- `countBySubject({})` 返回总数
- `countBySubject({status: "candidate"})` 返回 candidate 数

### 4.2 Owner routes 扩展（1 文件 + 1 test）

`apps/api/src/owner-routes.ts` 加 3 路由（接在现有 `/v1/owner/memories` POST + /:id/confirm + /:id/reject + DELETE 之后）：

```typescript
// GET /v1/owner/memories?status=candidate&limit=20&offset=0
app.get("/v1/owner/memories", async (c) => {
  const store = wiring.durableMemoryStore
  if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
  const subject = resolveOwnerSubject(env, conversationIdFromContext(c))
  const statusRaw = c.req.query("status") ?? "candidate"
  const status = parseStatus(statusRaw)  // "candidate" | "confirmed" | "rejected" | null
  if (!status) return c.json({ ok: false, reason: "invalid status" }, 400)
  const limit = parsePositiveInt(c.req.query("limit"), 20, 100)
  if (limit === null) return c.json({ ok: false, reason: "invalid limit" }, 400)
  const offset = parseNonNegativeInt(c.req.query("offset"), 0)
  if (offset === null) return c.json({ ok: false, reason: "invalid offset" }, 400)

  const items = await store.listBySubject({ subject, status, limit, offset })
  const total = await store.countBySubject({ subject, status })
  return c.json({
    items,
    total,
    hasMore: offset + items.length < total,
  })
})

// POST /v1/owner/memories/confirm-batch
//   body: { ids: string[] }
//   200: { confirmed: string[], failed: { id: string, reason: string }[] }
//   400: empty ids / non-array / > 50
//   503: store unavailable
app.post("/v1/owner/memories/confirm-batch", async (c) => {
  // ... (see §4.2.2)
})

// POST /v1/owner/memories/reject-batch
//   same shape, confirmDurableMemory → rejectDurableMemory
app.post("/v1/owner/memories/reject-batch", async (c) => {
  // ... (see §4.2.2)
})
```

#### 4.2.2 Batch handler 实现

```typescript
type BatchResult = {
  readonly confirmed: readonly string[]
  readonly failed: readonly { readonly id: string; readonly reason: string }[]
}

async function handleBatch(args: {
  readonly store: DurableMemoryStore
  readonly subject: string
  readonly ids: readonly string[]
  readonly transform: (record: DurableMemoryRecord, nowMs: number) => DurableMemoryRecord
}): Promise<BatchResult> {
  const nowMs = Date.now()
  const dedupedIds = Array.from(new Set(args.ids.map((s) => s.trim()).filter(Boolean)))
  const confirmed: string[] = []
  const failed: { id: string; reason: string }[] = []
  for (const id of dedupedIds) {
    try {
      const record = await args.store.get(id)
      if (!record) {
        failed.push({ id, reason: "not found" })
        continue
      }
      if (record.subject !== args.subject) {
        failed.push({ id, reason: "subject mismatch" })
        continue
      }
      if (record.status === "confirmed") {
        failed.push({ id, reason: "already confirmed" })
        continue
      }
      if (record.status === "rejected") {
        failed.push({ id, reason: "already rejected" })
        continue
      }
      const updated = await args.store.update(args.transform(record, nowMs))
      confirmed.push(updated.id)
    } catch (err) {
      failed.push({ id, reason: err instanceof Error ? err.message : "unknown error" })
    }
  }
  return { confirmed, failed }
}
```

Routes 调用：

```typescript
app.post("/v1/owner/memories/confirm-batch", async (c) => {
  const store = wiring.durableMemoryStore
  if (!store) return c.json({ ok: false, reason: "durable memory store unavailable" }, 503)
  const body = await c.req.json().catch(() => null) as { ids?: unknown } | null
  if (!body || !Array.isArray(body.ids)) {
    return c.json({ ok: false, reason: "ids must be a non-empty array" }, 400)
  }
  if (body.ids.length === 0) {
    return c.json({ ok: false, reason: "ids must be a non-empty array" }, 400)
  }
  if (body.ids.length > 50) {
    return c.json({ ok: false, reason: "batch too large (max 50)" }, 400)
  }
  if (!body.ids.every((x) => typeof x === "string" && x.trim().length > 0)) {
    return c.json({ ok: false, reason: "ids must be non-empty strings" }, 400)
  }
  const subject = resolveOwnerSubject(env, conversationIdFromContext(c))
  const result = await handleBatch({
    store,
    subject,
    ids: body.ids,
    transform: (record, nowMs) => confirmDurableMemory(record, nowMs),
  })
  return c.json(result)
})
```

### 4.3 Wechat commands 扩展（1 文件 + 1 test）

`apps/api/src/wechat-memory-commands.ts`:

```typescript
// 在 tryWechatMemoryCommand 中:

// 新增 /记忆候选
if (trimmed === "/记忆候选" || trimmed === "/memories-pending") {
  if (!store) return done("Durable Memory 存储不可用。", ["wechat-memory: no store"])
  const candidates = await store.listBySubject({ subject, status: "candidate", limit: 20 })
  const scoped = candidates.filter(
    (item) => !item.provenance.note || item.provenance.note.includes(active),
  )
  if (scoped.length === 0) {
    return done("暂无 candidate 记忆。", ["wechat-memory: candidates empty"])
  }
  const lines = [`候选 ${scoped.length} 条（${active}）：`]
  for (const item of scoped) {
    lines.push(`• ${shortId(item.id)} ${item.content.slice(0, 100)}${item.content.length > 100 ? "…" : ""}`)
  }
  return done(lines.join("\n"), ["wechat-memory: candidates list"])
}

// 扩 /确认记忆 支持 batch
if (trimmed.startsWith("/确认记忆")) {
  // ... existing store null check ...
  const tokenRaw = trimmed.slice("/确认记忆".length).trim()

  // NEW: parse comma-separated tokens
  const tokens = tokenRaw.includes(",")
    ? tokenRaw.split(",").map((s) => s.trim()).filter(Boolean)
    : tokenRaw ? [tokenRaw] : []  // empty → legacy "last 1" semantics

  const candidates = await store.listBySubject({ subject, status: "candidate", limit: 20 })
  const targets: { readonly token: string; readonly record: DurableMemoryRecord }[] = []
  const failed: { readonly token: string; readonly reason: string }[] = []

  if (tokens.length === 0) {
    // legacy: last 1 candidate
    const target = candidates.at(-1)
    if (!target) return done("没有待确认的 candidate 记忆。", ["wechat-memory: confirm none"])
    const updated = await store.update(confirmDurableMemory(target, Date.now()))
    return done(`已确认记忆 ${shortId(updated.id)}。`, [`wechat-memory: confirm ${updated.id}`])
  }

  // batch path
  // 注：tokens 受 `listBySubject({limit: 20})` 自然上限约束（取最近 20 个 candidate by updatedAt），
  //     超出该范围的 token 会进 `failed[]` with "not found"。owner 想看全量先 `/记忆候选`。
  for (const token of tokens) {
    const record = candidates.find((c) => c.id === token || shortId(c.id) === token)
    if (!record) {
      failed.push({ token, reason: "not found" })
      continue
    }
    targets.push({ token, record })
  }

  const confirmed: string[] = []
  for (const { record } of targets) {
    const updated = await store.update(confirmDurableMemory(record, Date.now()))
    confirmed.push(shortId(updated.id))
  }

  const okLine = confirmed.length > 0 ? `已确认 ${confirmed.length} 条：${confirmed.join(", ")}` : ""
  const failLine = failed.length > 0 ? `；失败 ${failed.length} 条：${failed.map((f) => `${f.token}=${f.reason}`).join(", ")}` : ""
  return done(
    `${okLine}${failLine}` || "无操作",
    [`wechat-memory: confirm-batch n=${confirmed.length} m=${failed.length}`],
  )
}
```

### 4.4 文档同步（3 文件）

#### 4.4.1 `butler-v5/DESIGN.md` §12 audit state note

在现有 D30 lock 6 行之后追加：

```markdown
> - **G3 batch candidate UI**（2026-09-01）：owner 撞 "candidate 多到处理不动" 痛点，本轮实施：
>   - Owner routes: `GET /v1/owner/memories?status=candidate&limit&offset` / `POST /v1/owner/memories/confirm-batch` / `POST /v1/owner/memories/reject-batch`
>   - Wechat: 新增 `/记忆候选` 命令；扩 `/确认记忆` 支持 `id,id,id` 逗号分隔 batch（兼容旧用法）
>   - 复用 `confirmDurableMemory`/`rejectDurableMemory` 单记录纯函数（domain 0 改）
>   - Persistence: `listBySubject` 加 `offset`；新 `countBySubject` 方法
>   - Subject mismatch 进 `failed[]` 而非 403（partial-failure 语义）
>   - 不引入新 first-class event；不引入新 Core Port；不动 §11.4 不默认建设项
> - **留待下轮**：G1 expires cleanup / G2 dedup / G4 Layer 1→2 auto-promote / G5 跨 project PK recall
```

#### 4.4.2 `butler-v5/DESIGN.md` §18 row 3 + §11 row 5 status note

- §18 line 656 "未触发" → "已 MVP ship + G3 batch candidate UI（2026-09-01）；留待下轮 G1 expires / G2 dedup / G4 auto-promote / G5 跨 project recall"
- §11 line 438 row 5 "memory_records 未触发" → "走 §12 durable_memories 路径满足 MVP；独立 memory_records 表待 §18 row 3 G3+ 触发"

#### 4.4.3 `butler-v5/packages/ports/port-catalog.md` §3

追加：

```markdown
- **MemoryService** — MVP 直调 `@butler/persistence/durable-memory-store` / `document-store` / `project-knowledge-store`，未物化 Core Port；与 Channel Port 类比，待 §7 audit 触发物化。Owner 路径走 `apps/api/src/{durable-memory-inject,project-knowledge-inject,wechat-memory-commands}.ts` + `owner-routes.ts`；Runtime 工具面 `recall_*` 直调 `@butler/persistence`。DESIGN §12 line 605 + §18 row 3（2026-09-01 G3）实证。
```

### 4.5 Arch guard 调整

`tests/architecture/section18-trigger-guard.test.ts` (D16)：检索涉及 Durable Memory 的 case，由 "0 invoke" 类 expected 改为 "MVP ship" 类 expected。具体 case 由 plan 阶段检索（不预设）。

`tests/architecture/section11-deferred-triggered.test.ts` (D22)：memory_records 行不动（已确认走 §12）。

### 4.6 边界遵守

- **§3 6 硬规则** (D33 lock): 不引入新依赖方向；Core 不 import adapters；本轮 0 新 Port；0 跨接缝
- **§20 16 invariant** (D26A + D26B): 不破坏 owner-only 命令入口（仍走 owner-routes + wechat-inbound-butler）；不破坏 RunEngine 唯一
- **§12 audit state** (D30 lock): 6 cases 全部保留 + 加 1 行 G3 batch UI 备注
- **§11.4 不默认建设**: 0 触（不引入 broker / bus / worker；不引入 cron）
- **§13 风险与自治** (D34 lock): batch 操作属 owner-only confirmed action（owner 主动 confirm/reject），不变更 §13 trigger 分类
- **§14 observability** (D21 + D23 + D24): 0 新 first-class event；沿用现有 per-id emit path；不破坏 D21 11 first-class + 3 workaround + 0 真缺 边界

---

## 5. 测试策略

### 5.1 Test cases（~22 cases）

| 文件 | case | 描述 |
|------|------|------|
| `apps/api/src/owner-routes.test.ts` | GET happy path | `?status=candidate&limit=20&offset=0` 返回 2 items + total=2 + hasMore=false |
| | GET paginated | `?status=candidate&limit=1&offset=1` 返回第 2 条 + hasMore |
| | GET invalid status | `?status=foo` → 400 |
| | GET invalid limit | `?limit=200` → 400 |
| | GET invalid offset | `?offset=-1` → 400 |
| | POST confirm-batch happy | 2 candidate ids → 200 `{confirmed: [id1,id2], failed: []}` |
| | POST confirm-batch dedup | `[id1,id1,id2]` → dedup 后 process once each |
| | POST confirm-batch partial | 1 candidate + 1 missing → 200 `{confirmed: [id1], failed: [{id2, "not found"}]}` |
| | POST confirm-batch already confirmed | 已 confirmed → `failed: [{id, "already confirmed"}]` |
| | POST confirm-batch subject mismatch | 跨 subject record → `failed: [{id, "subject mismatch"}]` |
| | POST confirm-batch store error | DB 抛错 → 200 + per-id `failed: [{id, "unknown error"}]`（per-id try/catch，整体不 500） |
| | POST confirm-batch empty `ids` | `{ids: []}` → 400 |
| | POST confirm-batch > 50 | 51 ids → 400 |
| | POST confirm-batch non-string id | `["id1", 123]` → 400 |
| | POST reject-batch happy | 2 candidate ids → 200 |
| | POST reject-batch already rejected | 已 rejected → `failed: [{id, "already rejected"}]` |
| `apps/api/src/wechat-inbound-commands.test.ts` | `/记忆候选` 列表 | 2 candidate → 输出 2 条 |
| | `/记忆候选` 空 | "暂无 candidate 记忆" |
| | `/确认记忆 id1,id2` batch | 2 confirmed |
| | `/确认记忆 id1,id2` partial | 1 confirmed + 1 failed |
| | `/确认记忆` 无参 regression | 最近 1 个（保持旧行为） |
| | `/确认记忆 <single>` regression | 单 token（保持旧行为） |
| `packages/persistence/src/durable-memory-store.test.ts` | `listBySubject({offset: 5})` | 跳过前 5 条 |
| | `listBySubject({offset: 0})` | 行为不变（regression） |
| | `countBySubject({})` | 返回总数 |
| | `countBySubject({status: "candidate"})` | 返回 candidate 数 |

### 5.2 Coverage target

80%+ on new code（owner-routes new handler + wechat-memory-commands new branches + store new methods）。

### 5.3 Regression scope

| 路径 | 风险 |
|------|------|
| Wechat `/记住` / `/记忆` | 0 改 → 0 regression |
| Wechat `/确认记忆` 无参 / 单 token | regression test 已列 |
| Owner 单 record `/v1/owner/memories` POST + `/confirm` + `/reject` + DELETE | 0 改 → 0 regression |
| Recall tools `recall_durable_memory` / `recall_document` / `recall_project_knowledge` | 0 改 → 0 regression |
| Durable Memory working-set inject | 0 改 → 0 regression |
| Project Knowledge CRUD + sync + K1 | 0 改 → 0 regression |

### 5.4 Test gates

| Gate | 目标 |
|------|------|
| typecheck | 0 错 (7/7 workspace projects) |
| lint | 0 错 0 警 |
| test (production) | +22 cases from D38 baseline（236 files → 238 files） |
| test:archived | 持平 22 files / 101 pass |

---

## 6. 文件 ops 清单（预估 ~10 file ops）

| 文件 | 操作 | 行数估计 |
|------|------|---------|
| `packages/persistence/src/durable-memory-store.ts` | 加 `offset` + 新 `countBySubject` | +25 / -2 |
| `packages/persistence/src/durable-memory-store.test.ts` | 加 4 cases | +80 |
| `apps/api/src/owner-routes.ts` | 加 3 routes + `handleBatch` helper | +120 |
| `apps/api/src/owner-routes.test.ts` | 加 10 cases | +200 |
| `apps/api/src/wechat-memory-commands.ts` | 加 `/记忆候选` + 扩 `/确认记忆` batch | +60 |
| `apps/api/src/wechat-inbound-commands.test.ts` | 加 6 cases | +120 |
| `butler-v5/DESIGN.md` §12 audit state + §18 + §11 status note | doc-only | +20 / -3 |
| `butler-v5/packages/ports/port-catalog.md` §3 + R12 sync note | doc-only | +8 / -2 |
| `tests/architecture/section18-trigger-guard.test.ts` | D16 Durable Memory cases 调整 | +10 / -10 |
| `tests/architecture/section12-knowledge-memory.test.ts` | D30 6 cases + 1 行 G3 备注 | +5 / 0 |

总预估: ~10 file ops / +648 prod code + test / +28 doc-only

---

## 7. 不做（明确范围外）

- **G1 expires cleanup job / cron / schedule**：requires 触发 §11.4 #5 (broker) 或 §18 #11 (独立 worker)；本轮不动
- **G2 dedup similar candidates**：需要 similarity function；与 §12 line 600 "当前不建设：无来源的经验沉积" 部分重叠；本轮不动
- **G4 Layer 1→2 auto-promote**：违反 §12 line 599 "当前不建设：Dream 两阶段自动巩固 / 无来源的经验沉积"；明确不做
- **G5 跨 project PK recall**：需要变更 `recall_project_knowledge` 工具语义（`tools.ts:478-479` "must match current conversation project"）；本轮不动
- **G6 model-side `ingest_document` 工具**：与 §12 line 599 "当前不建设：自动全盘索引" 冲突；明确不做
- **D22 §11 row 5 独立 memory_records 表**：已确认走 §12 durable_memories 路径；不动
- **新 Core Port（MemoryService）物化**：与 Channel Port 类比，待 §7 audit 触发；本轮 port-catalog.md §3 加待物化行
- **新 first-class event**：沿用现有 per-id emit path；不扩 §14 边界

---

## 8. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-01-durable-memory-batch-candidate-ui.md`（plan 阶段产出）
2. **实施**: 撤销 D16 arch guard case（如有）+ 扩 persistence + 3 routes + wechat commands + tests + DESIGN + port-catalog 同步
3. **验证**: typecheck + lint + test (production) + test:archived + arch guard pass
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D39-section12-batch-ui-2026-09-01.md`（仿 D30 / D38 格式）
5. **commit**: `fix(arch): D39 §18 row 3 + §12 G3 batch candidate UI`
6. **Handoff**: `.blackboard/shifts/2026-09-01-d39-batch-ui-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D40: G1 expires cleanup（需先决定 schedule 实现 — §11.4 #5 / §18 #11）
   - D41: G2 dedup + G5 跨 project recall
   - D42+: G4 auto-promote（仅当 owner 改变 §12 设计原则时）

---

## 9. 关联

- `butler-v5/DESIGN.md` §12 line 577-613 — 知识层与记忆
- `butler-v5/DESIGN.md` §18 line 653-668 — trigger guard
- `butler-v5/DESIGN.md` §11 line 438 — P0-P4 capability
- `butler-v5/packages/ports/port-catalog.md` §1 物化 Core Port + §3 待物化
- `packages/domain/src/knowledge/durable-memory.ts` — DurableMemoryRecord 4 字段 + 3 sourceKind
- `packages/persistence/src/durable-memory-store.ts` — DurableMemoryStore 接口
- `apps/api/src/owner-routes.ts` — owner route handlers
- `apps/api/src/wechat-memory-commands.ts` — wechat command surface
- `apps/api/src/durable-memory-inject.ts` — working-set inject (opt-in)
- `apps/api/src/project-knowledge-inject.ts` — working-set inject (opt-in)
- `tests/architecture/section12-knowledge-memory.test.ts` — D30 §12 6 cases
- `tests/architecture/section18-trigger-guard.test.ts` — D16 §18 4 cases
- `tests/architecture/section11-deferred-triggered.test.ts` — D22 §11 5 cases
- Memory: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D30-section12-knowledge-2026-08-31.md`
- Memory: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-deferred-trigger-conditions-2026-09-01.md`
- Memory: `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D38-port-catalog-channel-2026-08-31.md`
