# D46 — Repository Port 物化（2026-09-02）

**批次**：D46（Repository Port）· 主线：ports/persistence · 语言：TS

**目标**：把 Repository 从"⚪ 隐性承载（YAGNI）"物化为 ports 层 Repository Port。方式 A：先造触发条件（第二持久化实现 = in-memory runtime-store），再物化接口。推翻 D26B §20 #6 "Repository 在 persistence 而非 ports" 原 lock。

## 交付（2 commit，已备推 origin/main）

- **src/文档 commit**：in-memory RuntimeStore + Repository Port + arch guard + DESIGN §7.1/§7 + port-catalog + ports/index barrel + package.json exports
- **chore(blackboard) commit**：state.md + 本卡

## 改动清单

### 源码
- `packages/persistence/src/memory/runtime-store.ts`（新增）：`createInMemoryRuntimeStore(): RuntimeStore` —— 纯内存 Map，无 Drizzle/无 DB/无 IO，实现 domain `RuntimeStore` 合同（第二持久化实现触发）
- `packages/persistence/src/index.ts`：导出 `createInMemoryRuntimeStore`
- `packages/ports/src/core/repository.ts`（新增）：`RepositoryPort = RuntimeStore`（复用 domain 合同单一真相源，interface-only）+ re-export `RuntimeStore`；`packages/ports/src/index.ts` barrel `export *`；`package.json` exports `./core/repository.js`

### arch guard
- `tests/architecture/section7-1-repository.test.ts`（新增）：端口存在/导出 `RepositoryPort`/纯函数 0 IO/依赖向内（import domain 但非 persistence/runtime/adapters）/两 adapter 存在
- `section7-ports-main.test.ts` case #4：canonical 集加入 `repository.ts`
- `section7-1-port-snapshot.test.ts` C12：8→物化 filename 集加 `repository.ts`

### 文档
- `DESIGN.md §7`：快照 bullet（Repository Port）+ Interface-only 文件集 8→9 + 锁定方式（推翻 D26B #6）+ 状态表 Repository 行 ⚪→✅ + 概念表 adapter 加 in-memory + v5 总入口 7→9
- `port-catalog.md`：§1 表加 Repository 行；§3 待物化 Repository 移入 ✅；最近更新行

## 关键决策

- `RepositoryPort` **复用 domain `RuntimeStore` 合同**（type alias），不重复声明 20 方法 —— 单一真相源；ports 只声明端口归属。ports→domain 依赖是既有先例（event-store.ts import domain ActorRef）
- in-memory store 授权 scope 匹配为简化字段匹配（capability+subject+runId+digest+过期+未耗尽），不搬 `grantMatchesAction`/MCP scope 全部治理细则（测试/隔离替代品足够）
- 未改生产 wiring 消费侧（仍 type import domain `RuntimeStore`）——手不 re-wire 20+ consumer，避免范围膨胀；port 接缝由第二实现证明可替换

## 5-gate

typecheck 全包 PASS（含 protected-file WARN，非阻断）/ lint 0 警 / 全量 `CI= pnpm test` **254 files / 1491 pass / 1 skip / 0 fail**（vs D45 基线 252/1480，+2 测试文件 +11 用例：in-memory 8 + repository guard 3）/ arch guard 全绿 / file-size PASS。

## 验证（已闭环）

`CI= pnpm test` 全量回归绿；新增 in-memory 契约流单测 8 pass；repository arch guard 3 pass。无待 operator 复核项。**commit message 需含 `[MANUAL-OVERRIDE]`**（改到 protected `packages/ports/src/index.ts`）。

## 下一步

push origin/main。后续 batch 候选（D47 起）：exec 记账（若 owner 真撞）、Channel Port（等 Slack/Telegram 真接生产）。Repository Port 已闭环，memory 类（MemoryService, §12）按 §7 触发条件类比静候第二实现/隔离需求。