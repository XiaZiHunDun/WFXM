# D53a — Methodology Protocol (multi-round + prompt-freeze + fresh verification)

> **目的:** 解决 D47 (v8 PRD 3/3 REVERT, LLM temperature variance) + D50 (ship-claim miss) 复发风险, 把 verification 协议提升为一等公民。
>
> **适用:** D# / P# / B# / C# / D5x 任何触 LLM code path 的 batch (含 acceptance harness、realistic scenarios、e2e tests、未来 LLM eval)。
>
> **生效日期:** 2026-09-10 (D53a ship)。

---

## §0 Scope

**本协议适用对象**:
- `butler-v5/tests/acceptance/**/*.test.ts` 任何跑 LLM-driven acceptance 的 test
- `butler-v5/tests/e2e/**/*.test.ts` 任何触 LLM call 的 e2e
- `butler-v5/apps/cli/**/*.test.ts` 任何用 `--llm` 模式的 CLI test
- 任何 future ship (D# / P# / B# / C# / D5x+) 引入的新 LLM test 必须协议-compliant 才能 ship

**不适用**:
- 纯 unit test (`packages/*/src/**/*.test.ts` 纯函数逻辑, 不调 LLM)
- 纯 typecheck / lint / arch-guard
- 文档 / memory 改动 (虽然 D53c 走协议 verification, 但 verification 的是 impl 不变前提)

---

## §1 multi-round

**规则**: LLM-driven test 必须跑 N≥3 round, 聚合后才算 verdict。

**聚合规则**:
- **all** (默认): 3/3 round 都 pass 才算 pass。任何 round fail = test fail。
- **majority** (opt-in via `BUTLER_V5_AGGREGATION=majority`): ≥ ⌈N/2⌉ round pass 就算 pass (2/3 pass 算 pass)。

**环境变量**:
- `BUTLER_V5_MULTI_ROUND=N` — 显式指定 round 数 (默认 3)
- `BUTLER_V5_MULTI_ROUND=0` — opt-out, 跑 1 round (仅 fast iteration 临时用, ship 前必须 0→3)
- `BUTLER_V5_AGGREGATION=majority` — opt-in 多数规则 (默认 all)

**Rationale**:
- D47 实证: v8 PRD 3 round 都不同 verdict, 单 round verdict 不可靠
- N=3 是 cost / reliability sweet spot (D54+ 评估 per-scenario 是否需要 N=5)

**Anti-pattern**:
- ❌ 永远跑 1 round 然后 "看着对就过"
- ❌ N=3 但用 majority 默认 (应在 ship gate 用 all, fast iteration 才 majority)

---

## §2 prompt-freeze

**规则**: 一个 ship 期间, system prompt 在 ship 起点 snapshot 后冻结, 整 ship 不变。

**具体**:
- Ship 起点: `git rev-parse HEAD:apps/api/src/system-prompt.ts` (或对应文件) 记录为 baseline
- Ship 期间: 任何 `system-prompt.ts` / `system-prompt*.ts` / `prompts/*.ts` 改动 = ship 失败 (pre-commit hook 拦截)
- 中途要改 prompt: 拆为新 ship, 重新跑 baseline + verification

**Rationale**:
- Recordings 是 baseline; prompt 变了 baseline 失效, 比较无意义
- 防止 "我顺便修了个 prompt" 导致 acceptance 数字变化但无法归因

**Anti-pattern**:
- ❌ "system prompt 小改应该没事" → 拆 ship
- ❌ "把 prompt 改了顺便跑 acceptance" → 拆 ship

---

## §3 fresh verification

**规则**: Ship claim 必须引用 "本 ship" 的 full verify 输出, 不可引用前 ship 的 green output。

**Pre-ship checklist** (ship-claim 模板):

```markdown
## D53a ship verification

**Test results (本 ship, 2026-09-10 跑):**
- `pnpm test:methodology` — ✓ N/N
- `pnpm test:acceptance` — ✓ 41/41 N=3
- `pnpm test:full` — ✓ (1862 + ~20 new) N=3

**Lint / typecheck / arch-guard:**
- `pnpm lint` — ✓ 0
- `pnpm typecheck` — ✓ 0
- `pnpm arch-guard` — ✓ 0

**Files changed:** <列出本 ship 实际 commit SHA 与文件>
**No reference to:** D52 ship green / D49 ship green (严禁)
```

**Rationale**:
- D50 教训: D49 ship claim 引用了 last batch green (实际有 1 test fail + 1 pre-existing typecheck)
- 必须本 ship 自身的 fresh output 才能 ship

**Anti-pattern**:
- ❌ "上次 ship 是绿的, 这次改动小应该没事" → 必须 fresh verify
- ❌ Ship claim 写 "复用 D52 验证" → 必须本 ship 自己的 verification

---

## §4 baseline recording

**规则**: 每个 protocol-compliant run 产 recordings/ baseline; 后续 run diff 此 baseline。

**结构** (`tests/acceptance/recordings/.baseline-2026-09-10.json`):

```json
{
  "snapshotDate": "2026-09-10",
  "shipEvent": "D53a",
  "scenarios": {
    "<scenarioId>": {
      "status": 201,
      "replyLen": 123,
      "toolCalls": 0,
      "approvalCount": 0
    }
  }
}
```

**生成**:
- 首次 (D53a): baseline-generator 跑全 41 scenarios, 录当前状态, 写入 `.baseline-2026-09-10.json`
- 后续 ship: compareBaseline() 读 baseline + 跑当前, diff 输出

**比较规则**:
- `status` 变化 = 必报 (critical)
- `replyLen` 偏离 ≥ 50% = 报 (info)
- `toolCalls` / `approvalCount` 变化 = 报 (info)
- D53a 阶段: 报但不 fail (warning only); D54+ 可选升级为 fail

---

## §5 retrofit checklist

把现有 test 升级为 protocol-compliant 的 6 步:

1. **确认 test 触 LLM**: 读 test source, grep `sendWechatMessage` / `makeAcceptanceApp` / `app.llm` 等 marker
2. **Wrap 入口**: 把 `it()` callback 内容抽出为 `runScenario()` 函数
3. **包 N=3 runner**: `it()` callback 改 `runMultiRound(() => runScenario(), { rounds: env.rounds, aggregation: env.aggregation })`
4. **跑 1 demo**: 测 1 个 scenario, 验证 N=3 实际跑 3 次, 聚合正确
5. **扩到全量**: 套所有 scenarios, 跑全 acceptance
6. **验证 cost**: 记录 N=3 vs N=1 的 wall-clock 增加, baseline 写入

**Example** (realistic.test.ts retrofit):

```typescript
// Before
it(`${scenario.id}`, async () => {
  // ... scenario body
})

// After
it(`${scenario.id}`, async () => {
  await runMultiRound(
    () => runScenario(scenario, app, ctx),
    { rounds: 3, aggregation: "all" }
  )
})
```

---

## §6 anti-patterns (禁 list)

- ❌ 单 round verdict (跑 1 次, 失败 → 改代码 → 跑 1 次, 绿了 ship) → 必须 N=3 + 聚合
- ❌ 引用 last batch green (D50 教训) → 必须本 ship fresh verify
- ❌ Ship 期间改 system prompt → 拆 ship
- ❌ Majority 聚合用作 ship gate 默认 → 严 gate 用 all, majority 仅 fast iteration
- ❌ Baseline diff critical 变化静默接受 → 必须显式 acknowledge in ship claim
- ❌ "改动小不需要跑全量" → 任何 ship 必须全量 verify
- ❌ Pre-commit hook 误报就 retry 多次 → 用 `--no-verify` (新 commit 安全) 或 probe + `--no-verify` (amend)

---

## §7 D47 / D50 post-mortem (为何需要本协议)

### D47 — v8 PRD 3/3 REVERT

- **现象**: v8 PRD candidate A/B/C 三个方案, 每个跑 single round LLM eval, 3/3 都 REVERT (verdict 不稳定)
- **根因**: temperature model + 单 round snapshot 不构成稳定 baseline
- **协议防复发**: §1 multi-round 强制 N≥3 + 聚合; §2 prompt-freeze 防 prompt 漂移
- **未解**: D48 §3.2 "LLM 质量量化" 仍为 D51 decline, 协议不解决"什么算质量"

### D50 — D49 ship claim miss

- **现象**: D49 ship 时, 1 test fail (R8.x.11 wiring) + 1 pre-existing typecheck (wechat-task-digest-reply.ts:65) 都被 ship claim 漏报
- **根因**: ship claim 引用 "last batch green", 不是本 ship 自身 fresh verify
- **协议防复发**: §3 fresh verification 强制 ship claim 模板; §4 baseline 锁 D53a ship 时状态作 reference
- **未解**: methodology.test.ts 自身 false positive / false negative 率未实测; ship claim 模板的"本 ship"标记只能 catch 显式复用 last batch green, 隐性 race (e.g. pre-commit 改 + 跑出旧 green / 并行 agent 互相覆盖) 仍可绕过

---

**End D53a methodology protocol.**
