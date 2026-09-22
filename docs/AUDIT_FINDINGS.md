# Butler v5 — Audit Findings Index (D-series, 2026-08-31 → 2026-09-22)

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計; D80 梳理 +22 ship = 149) | **读者**: Owner / D-series 启动者 / 审稿人
> **关系**:
> - 功能清单 → [`FEATURES.md`](FEATURES.md)
> - 测试覆盖（含 PRE-EXISTING）→ [`TESTS.md`](TESTS.md)
> - TODO / deferral 视图 → [`TODO_DEFERRED.md`](TODO_DEFERRED.md)
> - 目标架构（§3-§20 不变量锚定）→ [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
> - D-series 累計 → [`ROADMAP.md`](ROADMAP.md)
> - 原始 `.audit/Dxx/...` — **gitignored**；on disk 可读（per D45 engineering-hygiene）；本表是聚合视图
> - 反馈 lessons → `.claude/projects/-home-ailearn-projects-WFXM/memory/`

> **范围**: 本表覆盖 **D69 → D74**（最近 6 cycles）的 raw findings + 主题聚类；D55→D68 早期 cycles 数据见各 cycle memo 或 `MEMORY.md` D-series 段；D75-D77 已 ship（含 raw findings 一并 ship）；D78-D79 docs/demo-batch ship（spec.md only）。

---

## 图例

- ✅ **shipped**（T1-T5 闭环）
- 📅 **deferred**（保留 record；下 cycle 触发）
- ❌ **don't-fix**（declined / structural）
- 🔄 **carry N cycles**（跨 cycle carry，第 N 次）
- 🆕 **regression**（D73 ship 引入的新问题）

## §0 Per-Cycle Findings（最近 6 cycles）

| Cycle | Cycle # | Raw Findings | must-fix | defer | dont-fix | 主题 | 备注 |
|-------|---------|--------------|----------|-------|----------|------|------|
| **D69** | 15th | 93 | 40 | 44 | 9 | CQ/SEC/SO | 5-ship atomic; validation defense sweep + cross-actor typed error + auth/WS hardening |
| **D70** | 16th | 97 | 42 | 45 | 10 | CQ/SEC/SO | CQ-010 silent no-op + owner-route HTTP + owner rate-limit + QR SSRF |
| **D71** | 17th | 96 | 46 | 39 | 11 | CQ/SEC/SO | MCP HTTP/SSE SSRF + symlink + Telegram/Slack user allowlist |
| **D72** | 18th | 91 | 40 | 39 | 12 | CQ/SEC/SO | actor column wiring + owner-jargon sweep + security trio D71 carry |
| **D73** | 19th | 94 | — | — | — | CQ/SEC/SO | 5-ship atomic; CQ-014 magic 30_000 + structural + audit emit actor + spec/scenario |
| **D74** | 20th | **65** | **23** | **33** | **9** | CQ/SEC/SO | **closure effectiveness -29 findings vs D73**; 13-cycle CQ carry-pattern detected |
| **Total** | — | **536** | **191+** | **200+** | **51+** | — | D69→D74 6 cycle density |

> **D74 closure effectiveness**: 65 findings（was 94 D73）— **-29 findings / -30.9%**。  5 themes A/B/C/D/E 全部 ship（per D74 T1-T5）。
> **13-cycle CQ carry-pattern detected** in D73: CQ-002/003/004/005 god-fn/file-split extractions 跨 cycle carry；D75 T1 通过 `handleOutboxMessage` 3-helper + workspace-tools undo module split + subagent-worker 807→773 + routes.ts channel-handler split 583→81 + new entry-point (routes/inbound.ts) 闭环。

## §1 Theme A: Owner-jargon sweep（最大持续主题）

> D69→D74 持续 theme；SO-001/SO-006/SO-007 等 carry 跨 3+ cycles。

| Finding | Cycle | Sites | Status | Closure |
|---------|-------|-------|--------|---------|
| **SO-001 owner-route `X store unavailable` English leak** | D69→D74 | 25+ sites | 📅 5 cycles carry | D74 T1 + D63 T2 lesson（M9 owner-jargon 同 batch 改测试） |
| **SO-002 telegram API failure English leak** | D69→D74 | 3 sites | 📅 2 cycles carry | D74 T1 |
| **SO-006 domain-layer English validator leak** | D74 | ~25 sites | ✅ shipped D74 T1 | single `safeOwnerErrorString` helper + 9 owner-route sites |
| **SO-007 attacker-controllable subject** | D72→D74 | 9 sites | 📅 3 cycles carry | per-action allowlist ~15 lines + 4 test updates |
| **SO-016 F3-replay scenario fixture text** | D72 | 1 fixture | ✅ shipped D72 T5 | F3 fixture text rewrite |
| **C-O-*/C-F*/D-owner-direct fixture text** | D74 | ~10 fixtures | 📅 1 cycle carry | D75+ spec scenarios |

**Lesson**（D63 T2）：owner-jargon 改 reply 字符串必须同 batch 改测试；D-series "G-7 角色分离"扩展为 M9 owner-jargon principle。

## §2 Theme B: Code Quality / Structural / God-fn

> D73 D74 5/5 themes B 命中（god-fn batch + 800-line cap）。

| Finding | File(s) | Lines | Status | Closure |
|---------|----------|-------|--------|---------|
| **CQ-002 `handleOutboxMessage` god-fn** | subagent-worker.ts:442-715 | 273 | 📅 2-4 cycles carry | D75 T1 [MANUAL-OVERRIDE] 3-helper extract |
| **CQ-003 `workspace-tools.ts` 800-line cap** | workspace-tools.ts | 811 | 📅 2 cycles carry | D75 T1 undo module split → workspace-tools-undo.ts |
| **CQ-004 `subagent-worker.ts` 800-line cap** | subagent-worker.ts | 801 | 📅 2 cycles carry | D75 T1 → 773 after CQ-002 extract |
| **CQ-005 `routes.ts` 583 lines** | routes.ts | 570 | 📅 2 cycles carry | D75 T1 channel-handler split 583→81 + new entry-point (routes/inbound.ts) |
| **CQ-008/CQ-009** | runSubagentWorker 59 lines / detectSpam 82 lines | — | 📅 1 cycle carry | D73 T4 extract |

**Lesson**（D75 T1 [MANUAL-OVERRIDE]）：god-fn batch 必须拆 helper 而非单改；§20 invariant `KNOWN_ENTRY_POINTS` update 同步。

## §3 Theme C: Security（SEC-001 → SEC-019）

> D63→D74 持续 security hardening；Telegram / Slack / WS / MCP / SSRF / DNS-recheck 多面。

### §3.1 D63→D74 SEC Findings

| Finding | Cycle | Status | Closure |
|---------|-------|--------|---------|
| **SEC-001 MCP HTTP/SSE SSRF** | D71 | ✅ shipped D71 T2 | `isBlockedMcpHost()` |
| **SEC-004/005 Telegram/Slack user allowlist** | D71 | ✅ shipped D71 T4 | channel-config FAIL-CLOSED |
| **SEC-006/008 owner-route subject + WS origin loopback** | D71 | ✅ shipped D71 T4 | isOriginAllowedForWsUpgrade |
| **SEC-001 Telegram webhook replay dedup** | D74 | ✅ shipped D74 T4 | mirror ilink-poller pattern (seen-msg-id cache + TTL) |
| **SEC-006 slackBotToken/telegramBotToken Secret<T> wrapping** | D74 | ✅ shipped D74 T4 | matches ilink.ts D72 T3 pattern |
| **SEC-002 WS caller allowlist (bearer auth)** | D74 | 📅 defer carry | D74+ bearer auth |
| **SEC-003 channel outbound cwd root** | D74 | 📅 defer carry | |
| **SEC-019 ws-subscribe cap** | D63 | ✅ shipped D63 T3 | cap on WS subscribe rate |

### §3.2 Fail-Closed vs Fail-Open Trend

| Channel | Pre-D63 | Post-D74 |
|---------|---------|----------|
| Telegram webhook | FAIL-OPEN (T2 → T3) | ✅ FAIL-CLOSED |
| Slack signing secret | FAIL-OPEN | ✅ FAIL-CLOSED (D63 T3) |
| Channel config | FAIL-OPEN | ✅ FAIL-CLOSED (D63 T3) |
| Wechat inbound auth | shared secret | ✅ FAIL-CLOSED + x-inbound-secret header |
| MCP HTTP/SSE | unfiltered | ✅ FAIL-CLOSED via isBlockedMcpHost |
| QR SSRF | iLink fallback | ✅ FAIL-CLOSED via isBlockedInboundUrl |

**Lesson**：SEC findings 趋势 = FAIL-OPEN → FAIL-CLOSED 收敛（per D63 / D70 / D71 / D74）。

## §4 Theme D: Spec/Scenario Cohesion（SO-013/014/016）

> Spec/Plan 一致性 + acceptance scenario 覆盖。

| Finding | Cycle | Status | Closure |
|---------|-------|--------|---------|
| **SO-013 injectAuditEvent signature** | D70 | ✅ shipped D70 T5 | signature unification |
| **SO-002 F3 spec clarification** | D71 | ✅ shipped D71 T5 | F3 chat-side 探针 |
| **SO-003 verify callback cleanup** | D71 | ✅ shipped D71 T5 | verify callback lifecycle |
| **SO-013 spec/scenario** | D74 | ✅ shipped D74 T5 | leftover |
| **SO-016 F3 fixture text** | D72 | ✅ shipped D72 T5 | fixture text rewrite |

## §5 Theme E: Dead-code / Knip（per cycle）

| Cycle | Knip findings | D53b deletion status |
|-------|---------------|------------------------|
| D60 | drift cleanup 6 knip | ✅ 87 真删 (D53b) |
| D70 | 6 knip deadcode | ✅ shipped D70 T2 |
| D74 | — | baseline locked per D53a |

**Baseline locked**: D53b (2026-09-11) 后 v5 codebase 0 TODO/FIXME/XXX/HACK markers；D53c 提议 `pnpm todo:check` CI gate（未实施）。

## §6 Cross-Cycle Amplification（cross-track 影响）

> D74 5 主题中 A/B/C 三主题交叉放大 — 不完整 D73 sweep 触发新 finding。

| Theme A (owner-jargon) | Theme B (domain-layer English) | Theme C (D73 regression) |
|--------------------------|--------------------------------|--------------------------|
| SO-001 (25 sites carry) | SO-006 (~25 sites via helper) | CQ-006 (`DEFAULT_LLM_TIMEOUT_MS` drift) |
| SO-002 (3 telegram) | single `safeOwnerErrorString` helper | CQ-007 (15_000 hardcode Telegram) |
| SO-003 (memories.ts batch) | + 9 owner-route sites | both → defaults.ts adoption incomplete |
| SO-004/005 (project-knowledge/documents) | Theme B architecturally cleanest | |

**Lesson**: D73 sweep 失败 = D74 cycle carry-pattern amplification；D-series rhythm: 每个 cycle 必须 fresh full verify (D50 lesson)。

## §7 Carry-Pattern Statistics

| Pattern | Cycles | Last seen | Closure strategy |
|---------|--------|-----------|------------------|
| Owner-jargon (SO-001..) | 5+ | D74 | M9 owner-jargon principle + 同 batch 改测试 |
| god-fn batch (CQ-002..005) | 4 | D75 T1 | 5-ship atomic + [MANUAL-OVERRIDE] + §20 invariant update |
| Security trio (SEC-001..008) | 0 | D74 | all shipped or bearer-auth defer |
| Spec/scenario (SO-013/016) | 0 | D74 | all shipped |

## §8 Notable Aggregate Metrics

> D55→D74 (20 cycles) ship 累計：

| Metric | Value | Source |
|--------|-------|--------|
| Total cycles | 20 | D55→D74 |
| Total ships | 100 | ROADMAP |
| Total audit findings (6 most recent cycles) | 536 | D69→D74 |
| Avg findings/cycle | ~89 | D69-D74 mean |
| D74 closure effectiveness | -29 findings vs D73 | best cycle |
| Themes A-E detected | 5 | D73-D74 |
| Carry cycles (33+ finding patterns) | 5+ | D69-D74 |
| Methodology N=3 verify | 100% cycles | D53a since D55 |
| Secrets GHA push | 0 leaks | D45 + D74 |

## §9 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单（含 §8 deferral 状态） | [`FEATURES.md`](FEATURES.md) §8 |
| 测试覆盖 | [`TESTS.md`](TESTS.md) |
| TODO / deferral | [`TODO_DEFERRED.md`](TODO_DEFERRED.md) |
| D-series 累計 + 维度候选 | [`ROADMAP.md`](ROADMAP.md) |
| 原始 audit findings (gitignored) | `.audit/D69/`, `.audit/D70/`, ..., `.audit/D74/` |
| Per-cycle summary | `.audit/D{69,70,71,72,73,74}/summary.md` |
| Per-track findings | `.audit/D{69,70,71,72,73,74}/{code-quality,security,spec-owner-ux}.json` |
| methodology N=3 baseline | `.audit/D53a/` + `.blackboard/state.md` |
| D-series lessons | `MEMORY.md` "Recent Batches" 段 |

---

**End of AUDIT_FINDINGS.md** | D80 cycle 26 inventory batch | **536 findings / 6 cycles / 5 themes**（D69→D74）