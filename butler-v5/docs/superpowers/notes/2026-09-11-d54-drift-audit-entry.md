# D54 — Drift Audit Entry (handoff from D53c, 2026-09-11)

> **目的:** D53c 闭环 D53 (D+C+A) 后, D54 (drift 对账) 准备 entry。
>
> **B track** 必须 D (methodology, D53a ship) 之后启, 否则 D47 REVERT 风险。当前 D53a ship ≥ 1 周, 风险低。

---

## Scope (从 D53 spec §1.2 + D53c handoff 累计)

### Pre-identified drift (must close in D54)

1. **D49 5-type 缺口** — impl 2 类 ChainEntry (write_file + run_command), spec 5 类 (write_file/edit_file/run_command/apply_patch/delete_file). D52 acceptance harness observed 5-type 缺口, D51 协议不修, route to D54.
2. **D49 6→5 phrases 缺口** — 缺 "撤销这批" 短语 (D49 spec 列 6, impl regex 实际 5+). D52 观察, D51 协议不修.
3. **memory "invertible flag" 不存在** — D49 spec 描述 `invertible: true` 字段 (表明可逆), impl 无此字段 (apps/api/src/workspace-tools.ts:35-41). D52 观察, D51 协议不修. **D54 decision: formalize (delete spec mention) or implement (add field).**
   - **D54 T5 closure (2026-09-11)**: 全文 grep `invertible` in `docs/superpowers/specs/2026-09-09-d49-multi-tool-chain-undo-design.md` → 0 hits。spec 实际上从未声明 `invertible: true` 字段 — 该 drift 在 spec 中不存在, 是 audit 误报 (`apps/api/src/workspace-tools.ts:35-41` 是 ALLOWED_RUN_COMMANDS 数组常量, 不是 `invertible` 字段位置)。**formalize 选择**: 在 D49 spec §4.6 加 "Per-kind Revert Semantics (no `invertible` flag)" 段, SSOT lock per-kind 行为 (write/edit/delete fully reversible; patch best-effort; command non-invertible) + 解释为什么故意不引入 boolean 字段。这把 audit 误报 lock 在 spec 中, 防后续 drift 重现。
4. **D52 acceptance harness 观察 ship claim vs impl drift** — D49 spec vs impl 5-type / 6-phrase / invertible 偏差. D51 协议不修, route to D54.
5. **D49-D53 期间新发现 drift** — D54 实施时 scan 发现 (D53a/b 已 ship, 可能引入新 drift).

### From D53b (code health) follow-up

6. **3 knip FPs** — `approveWaitingStep` / `denyWaitingStep` / `buildHonoApp` 是 knip 限制 (dynamic dispatch / test harness builder). D54 探索 knip `ignoreExports` 配置 or refactor to make them detectable.

### D53c 闭环 (D54 不再处理)

- ✅ recordings/ 35 vs 41 → D53c T7 formalize (6 placeholder entries in baseline JSON)
- ✅ vitest coverage scope → D53c T7 扩 6 packages
- ✅ realistic.test.ts file header "35" → "41" → D53c T7 文字 update
- ✅ D48 doc §3.3 text-vs-table drift → D53c T5 改 line 100-101 (closed)
- ✅ 2 test isolation flakes (subagent-multiturn + product-regressions) → D53b T7 (closed via D50 env pattern in harness.ts)

---

## D54 prerequisites

- D53a ship ✓ (2026-09-10, ≥ 1 周前, protocol baseline)
- D53b ship ✓ (2026-09-11, 0 drift after follow-up)
- D53c ship (本批) — deferral reeval 锁定 baseline + 闭环 4 drift items
- D54 spec 写 — drift 闭环 plan
- D54 plan 写 — task breakdown
- D54 ship — apply + verify per D53a protocol (N=3 fresh verify, ship claim 模板, 0 引用 prior batch green)

---

## D54 工作量预估

- 1-2d wall-clock
- D49 5-type 修可能扩大 scope (impl 3 类 + tests + 验证)
- D49 6→5 phrases 修 (~30 行 code + 5 acceptance scenarios update)
- memory "invertible flag" formalize vs implement 需 design decision (1 batch = 选一个)
- 3 knip FPs 可能 1 commit config update (`knip.json` ignoreExports)
- ship claim vs impl drift 闭环 (跟 D49 5-type 修一起, 1 commit)

---

## D54 ship gates (D53a protocol applied)

- 0 spec drift remaining (D49 5-type/6-phrase 闭环 + memory "invertible flag" 决策)
- 0 ship claim vs impl drift remaining (D52 观察闭环)
- 0 new drift introduced by D54
- `pnpm test:methodology` ✓ (D53a protocol 13 case unchanged)
- `pnpm test:acceptance` ✓ 81/81 N=3 (5 chain-undo scenarios 闭环后, scenario 内 assert 可能 adjust)
- `pnpm test:full` ✓ 1874+/1/0 N=3
- `pnpm lint` ✓ 0
- `pnpm typecheck` ✓ 0 (7/7 packages)
- `pnpm deadcode:knip` ✓ 0 true dead, 0 FPs (config updated or refactored)
- `pnpm arch-proxy` (tests/architecture/) ✓ 219/219 (新增 chain-undo coverage 后可能 +1 case)
- 1 fix-memory + MEMORY index

---

## D54 顺序与依赖

D54 = B (drift) sub-track of D53 meta-audit. 必在 D (D53a ship) 之后启, 当前 D53a ship 已 ≥ 1 周, 风险低。

依赖链:
- D53a protocol (multi-round + prompt-freeze + fresh verify) → 必要
- D53b code health baseline → 必要 (clean codebase for D54 work)
- D53c deferral reeval → 必要 (drift 状态已 SSOT-locked)
- D54 启动时间: D53c ship 完即可启

---

## D54 spec 范围 (D53a-style)

D54 spec 应包含:
- D53a protocol §3 fresh verification 引用 (每 ship claim 必须本 ship verify, 不复用 D53c green)
- D49 5-type 修的设计 (是否扩大 scope)
- memory "invertible flag" 决策 (formalize vs implement)
- 3 knip FPs 决策 (ignoreExports config vs refactor)
- ship claim vs impl drift 闭环 (D52 观察每个 item)
- 0 new drift 防御 (D49 5-type/6-phrase 修可能引入新 drift, N=3 verify)

D54 spec 不应包含:
- §18 / §11.4 / §11 任何 1 项重启 (D53c 闭环 0 trigger 撤销, D54 不重启)
- D48 3 gaps closure (3.1/3.2 declined, 3.3 partial closure shipped)
- 新 feature / 架构变更 / 性能优化

---

## 相关文件引用

- `butler-v5/docs/superpowers/specs/2026-09-10-d53-v5-meta-audit-design.md` (D53 整体 spec)
- `butler-v5/docs/superpowers/notes/2026-09-11-d53c-deferral-reeval.md` (D53c reeval 8 段 doc, §4.4 D54 entry 详细)
- `butler-v5/docs/superpowers/notes/2026-09-10-d53a-methodology.md` (D53a protocol, D54 ship claim 模板)
- `butler-v5/docs/superpowers/notes/2026-09-08-d48-owner-perspective.md` (D48 §3 3 gaps, D53c fix 后)
- `butler-v5/tools/deadcode-report.md` (D53b 3 knip FPs documented)
- `butler-v5/apps/api/src/workspace-tools.ts` (D49 5-type / 6-phrase / invertible flag actual impl)

---

**End D54 entry doc.**
