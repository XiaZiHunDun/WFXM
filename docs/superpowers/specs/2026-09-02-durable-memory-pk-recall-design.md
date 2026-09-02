# Cross-Project Project Knowledge Recall — 设计 spec (G5)

> **For agentic workers:** 配套实施计划见 `docs/superpowers/plans/2026-09-02-durable-memory-pk-recall.md`（plan 阶段产出）。
> **背景**：D30 §12 主体 + D39 G3 batch UI + D40 G1 expires + D41 G2 dedup + D42 G4 auto-promote 已 ship。owner 真撞的第二场景是 "WFXM 的项目知识在另外 project（如 LingWen）也有，recall 现在只能查当前 project"。G5 闭环 §12 知识层 recall — 让 `recall_project_knowledge` 支持跨 project 召回（默认仍当前 project，向后兼容）。
> **优先级**：G5 only — 跨 project PK recall；动 `recall_project_knowledge` 工具语义。
> **影响面**：`packages/persistence/src/project-knowledge-store.ts` 加 1 能力 (`listAllProjects` / `listByProjects`)；`packages/domain/src/knowledge/project-knowledge.ts` 加 1 纯函数 (`expandRecallProjectIds` / `aggregateRecallResults`)；`apps/api/src/tools.ts` 更新 `recall_project_knowledge` 工具 descriptor + 实现（从 "deny cross-project" 改为 "默认当前 project + 显式多 project"）；arch guard + DESIGN §12/§18 + smoke 脚本验证。
> **预估 ops**：~8 file ops / ~+400 prod+test lines / +10 doc-only lines / 5 commits (1 spec + 4 impl) / ~28 test cases

---

## 1. 目标

闭环 §12 知识层 recall gap — G5 跨 project PK recall：

1. **默认当前 project（向后兼容）** — 不传 `projectId` / `projects` 时，`recall_project_knowledge` 仍只召回当前对话 project（现有行为, P0）。显式传时才跨 project。
2. **显式跨 project** — `projectId` 可指向任意 project（不再强制等于当前对话 project）；或新增 `projects` 参数（逗号分隔列表 / `"*"` 全量）。
3. **多 project 聚合** — 跨 project 结果带 projectId 标签，避免歧义。
4. **沿用现有 substring recall** — 不引入 embedding；每组 project 内走 `selectProjectKnowledgeForRecall`（substring filter + limit + 按 updatedAt 倒序）。
5. **§12 line 549 + line 593 + D30 case #6 lock 保持** — Project Knowledge 不冒充个人记忆；embed-free。
6. **不改 §13 治理** — recall 是只读 low-risk 工具（risk="low" 不变），无需 grant/approver。
7. **§18 row 3 收口** — G5 完成后 §12 G3+G1+G2+G4+G5 → design 完整闭环；§18 row 3 从 "留待下轮 G5" 移除。

---

## 2. 决策汇总（brainstorming 已确认）

| 维度 | 决策 |
|------|------|
| 动机 | **(b) 架构补全** — D30-D42 §12 4 治理链路已 ship；G5 补上 recall 跨 project 语义 gap |
| 默认范围 | **默认当前 project（向后兼容）** — 不传 `projectId`/`projects` 时只召回当前对话 project；显式传才跨 project（最小惊讶，召回成本可控） |
| 跨 project 触发方式 | **新增 `projects` 参数（逗号分隔 / `"*"` 全量）+ `projectId` 可指向任意 project** — 向后兼容：现有 `projectId` 语义放宽为可跨 project；新参数 `projects` 提供批量/全量 |
| 参数冲突 | **`projectId` 与 `projects` 同时传 → 用 `projects` 优先**（等价 "全量列表"）；都不传 → 当前 project |
| 当前 project 推导 | 沿用 `resolveProjectKnowledgeInboundProjectId`（inbound map 映射，如 `wechat→WFXM`） |
| 跨 project 聚合 | **带 projectId 标签** — 每条结果前缀 `[project:<projectId>]`；多 project 时按 project 分组显示 |
| 结果排序 | 每 project 内按 `selectProjectKnowledgeForRecall`（query filter + updatedAt 倒序 + limit）；跨 project 不重排序（保持 project 分组稳定） |
| limit 语义 | 全量限制：`limit` 作用于总结果；每 project 内部 limit = `Math.ceil(limit / projectCount)` 预算，避免撤回超发 |
| Embed-free | **保持** — 0 embedding column；沿用 substring recall（§12 line 593 + D30 case #6 lock） |
| 治理 | **不变** — recall 是只读 low-risk；0 grant / approver / policy |
| First-class event | **0 新增** — audit log 走现有 operator log 模式 |
| §18 关系 | **G5 不进 §18 row 3 表** — 是 §12 recall 语义补全，非 trigger-conditioned；§18 row 3 收口（从 "留待下轮 G5" 移除） |
| Arch guard | D30 §12 suite 扩 1 case：`tools.ts` recall 实现不再含 `"cross-project project knowledge recall denied"` + `listByProjects` 存在 |

---

## 3. 现状与不一致

### 3.1 已 ship（D42 G4 闭环后）

- D30 §12 6 cases + D39 G3 + D40 G1 + D41 G2 + D42 G4 共 10 cases arch guard lock
- §12 line 593 + D30 case #6 lock：embedding 默认不启用
- §3 6 硬规则 (D33) + §20 16 invariant (D26A + D26B) + §11 5 子段 audit 收口
- §18 row 3 🟡 MVP ship + G3 + G1 + G2 + G4；留待下轮仅 G5

### 3.2 真缺（1 gap）

- **`recall_project_knowledge` 单 project 限制**：`apps/api/src/tools.ts:712` 返回 `"cross-project project knowledge recall denied"`，owner 无法 recall 其他 project（如 WFXM 对话里查 LingWen 的项目知识）。该 deny **无测试锁定**（grep 无 `cross-project` 测试），语义放宽安全。

### 3.3 Persistence 缺口

- `ProjectKnowledgeStore` 无 `listAllProjects`（返回全部 projectId）或 `listByProjects`（多 project 批量召回）能力
- 现有 `listByProject` 只支持单 project
- 无 project registry 表（projectId 只是 `project_knowledge_items` 列）；跨 project = 扫 `projectId` 列 distinct，不新建 registry

### 3.4 文档 drift

- DESIGN §12 audit state "留待下轮：G5 跨 project PK recall" — 本 spec 实施后移除
- DESIGN §18 row 3 "留待下轮 G5 跨 project recall" — 收口为 "G5 跨 project recall ship"

---

## 4. 设计

### 4.1 Persistence 扩展（1 文件）

`packages/persistence/src/project-knowledge-store.ts`（+2 方法）：

```typescript
/** 返回全部存在的 projectId（去重），用于 "*" 全量召回。 */
listAllProjects(): Promise<readonly string[]>

/** 多 project 批量召回 —— 对每个 projectId 独立执行 listByProject 语义并铺平。 */
listByProjects(input: {
  readonly projectIds: readonly string[]
  readonly perProjectLimit?: number
}): Promise<readonly ProjectKnowledgeRecord[]>
```

- `listAllProjects`：`SELECT DISTINCT project_id FROM project_knowledge_items`。
- `listByProjects`：对每个 projectId 调 `listByProject({projectId, limit: perProjectLimit})` 并 `flat()`；不跨 project 排序（保持分组稳定）。persistence 内部对每个 project 独立 limit，避免单 project 拖垮总预算。

### 4.2 Domain 纯函数（1 文件）

`packages/domain/src/knowledge/project-knowledge.ts`（+2 纯函数）：

```typescript
/**
 * G5: 展开 recall 目标 projectId 集合。
 * - 不传 projectId/projects → [当前 project]（由调用方传 contextProjectId）
 * - projects === "*" → 全量（listAllProjects）
 * - projects 逗号分隔 → 展开并 trim/去重
 * - projectId 单值 → projects 缺席时使用
 */
export function expandRecallProjectIds(input: {
  readonly contextProjectId: string            // resolve 后的当前 project（缺陷时为空串）
  readonly requestedProjectId: string          // 显式 projectId 参数（已 resolve）
  readonly projects?: string                   // 逗号分隔 / "*"
  readonly allProjectIds: readonly string[]    // listAllProjects 结果（仅当需要全量时）
}): { readonly ok: true; readonly projectIds: readonly string[] } | { readonly ok: false; readonly reason: string }
```

- `projects === "*"` → 返回 `allProjectIds`；空 → `{ ok:false, reason:'no projects known' }`。
- `projects` 逗号分隔 → split + trim + 去重（空串过滤）。
- `projects` 缺席时用 `requestedProjectId || contextProjectId`。
- 结果空 → `{ ok:false, reason:'projectId is required for project knowledge recall' }`（保持现有错误文案）。

```typescript
/**
 * G5: 多 project 召回结果聚合。
 * - 单 project → 保持原有 snippet 格式（无 project 前缀，向后兼容）。
 * - 多 project → 每个结果加 `[{projectId}]` 前缀，并按 project 分组。
 */
export function formatCrossProjectRecall(input: {
  readonly query: string
  readonly limit: number
  readonly byProject: readonly { readonly projectId: string; readonly records: readonly ProjectKnowledgeRecord[] }[]
  readonly formatSnippet: (r: ProjectKnowledgeRecord) => string
}): string | null  // null = 无匹配
```

### 4.3 工具更新（1 文件）

`apps/api/src/tools.ts`（更新 `makeRecallProjectKnowledgeTool` + descriptor）：

- **descriptor**：`parameters` 增 `projects` 字段（可选 string，描述 "逗号分隔 projectId 列表，或 `*` 全量；默认不传 = 当前 project"）；`projectId` 描述改为 "可选 project id override（可跨 project；与 projects 冲突时 projects 优先）"。
- **实现逻辑**：
  1. `resolveProjectKnowledgeInboundProjectId` 当前 project（沿用）。
  2. 显式 `projects`/`projectId`（各 resolve）。
  3. **移除** `if (resolvedContext && requestedProjectId !== resolvedContext) return cross-project denied` 这段逻辑（G5 核心改动）。
  4. `expandRecallProjectIds` 展开目标 projectId 集合（`"*"` 时先 `listAllProjects()`）。
  5. `store.listByProjects`（或循环 `listByProject`）拉取；`selectProjectKnowledgeForRecall` + `formatCrossProjectRecall` 聚合。
  6. 空结果 → `"（无匹配的项目知识条目）"`（保持现有文案）。

### 4.4 测试策略（~28 cases）

| Suite | Cases |
|-------|-------|
| `persistence/src/project-knowledge-store.test.ts` (扩 ~8) | `listAllProjects` 4 (empty / 单 project / 多 project / distinct) + `listByProjects` 4 (空 / 单 / 多 / perProjectLimit) |
| `domain/src/knowledge/project-knowledge.test.ts` (扩 ~10) | `expandRecallProjectIds` 6 (context 默认 / 显式单 project / projects 逗号 / "*" 全量 / 冲突 projects 优先 / 空结果 error) + `formatCrossProjectRecall` 4 (单 project 无前缀 / 多 project 分组 / query 过滤 / 空) |
| `apps/api/src/tools.test.ts` (扩 ~8) | recall 默认当前 / 显式跨 project / projects 逗号 / "*" 全量 / projectId 缺失 error / limit 预算 / project 标签格式 / 空结果文案 |
| `tests/architecture/section12-knowledge-memory.test.ts` (扩 1) | G5 Case: `tools.ts` 不再含 `cross-project project knowledge recall denied` + `listByProjects` 存在 |

### 4.5 边界遵守（DESIGN §段）

- §3 6 硬规则 (D33 lock): 0 触（domain 接受 records 纯函数；persistence 是 driven adapter；tools 是 delivery）
- §20 16 invariant (D26A + D26B): 0 触（不新增 Core Port；不新增 worker；0 embedding）
- §12 D30-D42: 保留 + 加 1 G5 case；§12 line 549 保持（不冒充；projectId 标签是 recall 来源说明，非 memory 语义）；§12 line 593 embed-free 保持
- §13 风险与自治: 0 触（recall 只读 low-risk）
- §14 observability: 0 新 first-class event
- §11 append-only: 0 触（无 migration；只读查询）
- §18 row 3: 收口（从 "留待下轮 G5" 移除）；G5 不进 §18 row 3 表
- §7.1 port snapshot: 0 新 Core Port（复用 ProjectKnowledgeStore）

---

## 5. 文件 ops 清单（预估 ~7 file ops）

| 文件 | ops | 说明 |
|------|-----|------|
| `packages/persistence/src/project-knowledge-store.ts` | +35/-0 | `listAllProjects` + `listByProjects` |
| `packages/persistence/src/project-knowledge-store.test.ts` | +120/-0 | ~8 cases |
| `packages/domain/src/knowledge/project-knowledge.ts` | +70/-0 | `expandRecallProjectIds` + `formatCrossProjectRecall` |
| `packages/domain/src/knowledge/project-knowledge.test.ts` | +110/-0 | ~10 cases |
| `apps/api/src/tools.ts` | +55/-12 | 更新 descriptor + 实现（移除 deny，加跨 project + 聚合） |
| `apps/api/src/tools.test.ts` | +110/-0 | ~8 cases |
| `tests/architecture/section12-knowledge-memory.test.ts` | +25/-0 | G5 case |
| `butler-v5/DESIGN.md` | +4/-2 | §12 audit state G5 + §18 row 3 收口 |

总预估: ~8 file ops / +400 prod+test / +6 doc-only

---

## 6. 不做（明确范围外）

- **embedding-based recall**: §12 line 593 + D30 case #6 lock；明确不做
- **Project registry 表 / project 元数据**: 无 registry 需求；跨 project 扫 `project_knowledge_items.projectId` distinct 足够
- **跨 project 排序（global rank）**: 复杂度爆炸；保持 per-project 分组 + 每 project updatedAt 倒序
- **recall_document / recall_durable_memory 跨 project**: 仅动 `recall_project_knowledge`；其他 recall 工具语义不变
- **注入 working-set 跨 project**: working-set 注入保持当前 project；cross-project 仅作为显式 recall 工具能力
- **Owner project whitelist / 授权控制**: 所有 projectId 都是 owner 自己的项目；0 外部信任边界（owner workspace）
- **Per-project limit 指数分配优化**: 用预算 `Math.ceil(limit/count)`；不做自适应权重
- **New Core Port**: 复用 ProjectKnowledgeStore；与 §7 audit 一致
- **Audit log 每调用**: recall 是低价值只读；0 新 first-class event

---

## 7. 触发链 & 后续

本 spec 完成后：

1. **写 plan**: `docs/superpowers/plans/2026-09-02-durable-memory-pk-recall.md`（plan 阶段产出）
2. **实施**: 4 tasks (T1 persistence + T2 domain + T3 tools + T4 arch guard + DESIGN sync)
3. **验证**: typecheck + lint（每 commit 后跑）+ `CI= pnpm test` (production) + test:archived + arch guard pass（用 `CI= pnpm test`，本 AI 沙箱注入 `CI=true`）
4. **记忆**: 写 `~/.claude/projects/-home-ailearn-projects-WFXM/memory/project-fix-D43-section12-g5-pk-recall-2026-09-02.md`
5. **commit**: 5 commits (1 spec + 4 impl) with conventional commit format
6. **Handoff**: `.blackboard/shifts/2026-09-02-d43-g5-pk-recall-handoff.md`（冷启卡）
7. **后续 batch 候选**（按 owner 真撞顺序）:
   - D44: 工程治理 (pre-commit hook line 113 / dead code / refactor-clean)
   - D45+: D42 follow-up（T2 `confirmDurableMemory` 旁路 `promotedBy='owner'` + DESIGN placeholder dates）

---

## 8. 关联

- D30 §12 audit state (10 cases lock) — `memory/project-fix-D30-section12-knowledge-2026-08-31.md`
- D39 §12 G3 batch UI — `docs/superpowers/specs/2026-09-01-durable-memory-batch-candidate-ui-design.md`
- D40 §12 G1 expires — `docs/superpowers/specs/2026-09-01-durable-memory-candidate-expires-cleanup-design.md`
- D41 §12 G2 dedup — `docs/superpowers/specs/2026-09-01-durable-memory-dedup-design.md`
- D42 §12 G4 auto-promote — `docs/superpowers/specs/2026-09-01-durable-memory-auto-promote-design.md`
- §12 line 549/593 — `DESIGN.md` §12 主规则（Project Knowledge ≠ 个人记忆 / embed-free）
- §18 row 3 — `DESIGN.md` line 804（收口 "留待下轮 G5"）
- §3 6 硬规则 (D33 lock) — `memory/project-fix-D33-section3-dependency-2026-08-31.md`
- §20 16 invariant (D26A + D26B) — `memory/project-fix-D26A-section20-batch-A-2026-08-31.md` + `memory/project-fix-D26B-section20-batch-B-2026-08-31.md`
- ProjectKnowledgeStore — `packages/persistence/src/project-knowledge-store.ts`
- `resolveProjectKnowledgeInboundProjectId` — `packages/domain/src/knowledge/project-knowledge.ts:69`

---

**Spec version**: v1 (brainstorming closed 2026-09-02)
**Spec status**: awaiting user review