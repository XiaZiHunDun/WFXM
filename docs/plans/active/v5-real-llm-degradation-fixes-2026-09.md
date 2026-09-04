# v5 真实 LLM 行为降级修复合规（4 类问题）

> **交接对象**：Claude Code（后续开发）
> **触发**：2026-09-04 真 LLM 录音 (`butler-v5/scripts/acceptance/record-real-llm.ts`) 跑完 35 scenarios + diff baseline (本 PRD §3) 发现 4 类 model-side 退化
> **主线**：`butler-v5` 唯一活动主线；v4 已退役
> **录音 baseline**：`butler-v5/tests/acceptance/scenarios/recordings/{A1..D5}.json` + `_summary.md` (gitignore)
> **完成归档**：完成后在本文 §6 增一行 commit hash + 验证结果

## 1. 目标与动机

`35 realistic owner-task scenarios` 跑出 6 个 product-layer gap 已在 2026-09-04 收口（P0/P1/P2 三批）。但 2026-09-04 真 LLM 回放 `record-real-llm.ts`（首次 baseline）暴露了**模型侧而非产品侧**的 4 类降级：

| # | 问题 | 录音证据 |
| --- | --- | --- |
| ① | **D1 loop exhausted fallback** | `D1` 5 iter 不收敛 → stub fallback（`_summary.md` D1 latency 21,860ms 3 turns，最终 decision=`Finish`） |
| ② | **A10/C10 approval over-trigger** | `A10` fixture 期望 Respond 实际 WaitForApproval；`C10` 同 — 模型用 `find` 命令找文件触发 approval（**不是 PRD 初判的 `git log`**，见决策 doc `v5-real-llm-over-trigger-decision-2026-09.md`）|
| ③ | **12 invalid JSON decode** | 模型吐自然语言而非 decision JSON；harness 降级但 user 看到的是 stub reply |
| ④ | **2 unknown tool `WaitForApproval`/`Respond`** | `A10` 模型杜撰工具名 decoder fail |

录音共 240s / 35 scenarios / 43 turns / 12 invalid JSON / 2 unknown tool / 1 loop exhausted。所有"decision mismatch"（9 case）实际是**模型比 fixture 更谨慎**（read-before-write / ask-before-edit），仅 D1 是真退化。

**目标**：让 v5 wrap-around 真 LLM 不再触发 4 类降级 — prompt/decoder/policy 三层各归其位。**非 fixture 调优**（fixture 已反映 v5 已实现能力，模型行为超出不算 bug）。

## 2. Scope

### 2.1 In scope

| # | 工作 | 备注 |
| --- | --- | --- |
| 1 | D1 5-iter 不收敛 → fallback reply 明确化 + prompt 收口 | §5 P1 |
| 2 | A10/C10 approval over-trigger 评估：fixture 偏松 or policy 偏严？| §5 P2 |
| 3 | decoder 容错：retry 一轮 + 落 raw 到 audit | §5 P3 |
| 4 | tool schema 暴露：白名单校验拒 `WaitForApproval`/`Respond` 杜撰 | §5 P4 |
| 5 | 35 scenarios 重跑：`_analyze.md` 重新生成 + diff baseline | §5 P5 |
| 6 | 5 gate 全绿：typecheck / lint / 全量测试 / 录音 35/35 pass / 无新退化 | |

### 2.2 Out of scope

- Fixture 重写（降低验收严格度，反向操作）
- LLM provider 切换（仍是 MiniMax-M3[1m]，录音 baseline 锁定）
- Decision 强制 schema 改 OpenAI function calling（结构性大改，另立 ADR）
- Channel Port / MemoryService 等 §18 row 3 延后项

## 3. Diff baseline 数据（来自 `recordings/` 第一轮 + `_fixtures.ts`）

**Aggregate**：

- scenarios: 35 / 35 recorded
- decision match: 23 / 32 = **72%**（其余 3 个 fixture 不约束 finalDecision）
- approval match: 30 / 35 = **86%**
- tools: expected≥16, actual=48 (+32) — 模型探索更充分，**非退化**
- total latency: 240,327ms (avg 6,864ms/scenario)

**Decision mismatch 9 case 分类**：

| # | ID | Fixture 期望 | 真实 LLM | 评价 |
| --- | --- | --- | --- | --- |
| 1 | A2 | WaitForApproval 立即批 user.ts | read 后 Respond | ✅ 模型更稳 |
| 2 | A5 | WaitForApproval 批 foo.ts 删 import | "文件不存在" Respond | ✅ 模型更准 |
| 3 | A6 | WaitForApproval 批 utils.ts timeout | "没找到 utils.ts" Respond | ✅ 模型更准 |
| 4 | **A10** | Respond（无 approval）| WaitForApproval 批 `find . -maxdepth 3 -name package.json` | ⚠️ **A10 = P2 主因**（模型应用 read_file，误用 find via run_command） |
| 5 | C8 | WaitForApproval 批写文件 | "你想写什么？" Respond | ✅ 模型更稳 |
| 6 | **C10** | Respond（无需 approval）| WaitForApproval 批 `find . -maxdepth 2 -iname readme*` | ⚠️ **C10 = P2 主因**（同上，模型应用 read_file） |
| 7 | **D1** | WaitForApproval | Finish + stub | ❌ **P1**（loop exhausted）|
| 8 | D3 | WaitForApproval 批 user.ts | "没看到 user.ts" Respond | ✅ 模型更准 |
| 9 | D5 | WaitForApproval 批 /debug | "目录是空的" Respond | ✅ 模型更稳 |

**Degrade count**：invalid JSON 12 / unknown tool 2 / loop exhausted 1。

## 4. 关键机制 / 约定

- **Baseline 锁定**：`butler-v5/tests/acceptance/scenarios/recordings/` (gitignore) 是 §3 数据源；任何 §5 改动必须重跑录音 + diff 比对 baseline，禁止"凭感觉改"。
- **fixture 不动**：`tests/acceptance/scenarios/_fixtures.ts` 是验收 expected target，反映 v5 设计意图；LLM 行为超出 fixture 不算 bug。
- **decision mismatch ≠ bug**：72% match 中失配 9 个 7 个是 quality improvement；只修 D1/A10/C10/D2-D4（true degradation）。
- **5-gate 优先**：typecheck/lint/全量测试/35 scenarios pass/无 new degrade。**`BUTLER_V5_PGLITE_DATA_DIR` 跨重启测试保留。**

## 5. 待办（按优先级）

### P1: D1 loop exhausted fallback 修复

**目标**：5 iter 不收敛时 fallback reply 写明"无法收敛，需澄清"而非沉默 stub；prompt 加收敛提示。

**改动**：

- `packages/runtime/src/conversation-loop.ts`：`loop exhausted` 路径改显式 return `{ decision: "Finish", reply: "[需要澄清] 模型未在 5 轮内收敛，请补充信息。" }`，audit 落 `reason: "loop_exhausted"`
- `apps/api/src/system-prompt.ts`：plan role prompt 加收敛信号 — "若 3 轮仍未拿到足够信息，主动 ask follow-up"
- 新增 acceptance case：scenario D1 加 followUp，模拟 2 turn 后收敛

**验收**：重跑录音 D1 latency 应 < 15s / 2 turns；`finalDecision === "Respond"` 含澄清文本。

### P2: A10/C10 approval over-trigger 评估

**目标**：明确是 fixture 偏松 or policy 偏严。**不立即改 code**，先产出评估文档。

**改动**：

- `docs/plans/decisions/v5-real-llm-over-trigger-decision-2026-09.md`（新建）：评估每个 over-trigger case
  - A10 fixture: model expects RunCommand 不需 approval for `git log`；真实模型看到 `cmd="git log"` 也触发 → **fixture 偏松（v5 设计意图下 ls/git log 不需 approval）** — 但 `args=[full path] → 可能风险` 需重新评估
  - C10 fixture: model expects `ls /foo` 也不需 approval；真实模型触发 → 评估 ls + 绝对路径是否需 approval
- 决策记录走 `feedback-channel-trigger-scope` 3 选项协议

**验收**：决策 doc 落地 + 接受"fixture 偏松"或"policy 偏严"任一立场。

### P4: tool schema 暴露白名单

**目标**：模型杜撰 `WaitForApproval`/`Respond` 等 fake tool name 时立即报错而非 push error result。

**改动**：

- `packages/runtime/src/conversation-loop.ts`：tool name 白名单从 LLM router config 暴露 — `AVAILABLE_TOOLS` 列表从 `apps/api/src/wechat-tools.ts` 注入
- decoder 在 tool name 不在白名单时：`{ kind: "error", reason: "unknown_tool", name, availableTools }` 而非 pass through
- audit 落 `reason: "unknown_tool"` + 落 raw model output

**验收**：重跑录音 A10 unknown tool 0 case（不再杜撰 WaitForApproval/Respond）。

### P3: decoder invalid JSON 重试

**目标**：12 invalid JSON 退化中至少 8 改成 retry 一轮后成功。

**改动**：

- `packages/adapters/src/llm-decoder.ts`：decodeDecision fail 时 retry with schema prompt — `decodeDecision(raw, { retry: true })` 加 1 round schema hint
- 仍 fail → 落 raw 到 audit `reason: "invalid_json_after_retry"`，**不再 throw**，落 degraded reply

**验收**：重跑录音 invalid JSON 计数从 12 降到 ≤ 4。

### P5: 35 scenarios 重跑 + diff baseline

**目标**：所有 P1-P4 落地后 35 scenarios 重跑；`_analyze.md` 重新生成；diff baseline 对比。

**改动**：

- `butler-v5/tests/acceptance/scenarios/recordings/` 全清 + 重录
- `_summary.md` 重新生成
- 新 `_analysis.md`（手工）记录 35 case diff vs baseline

**验收**：新 `_analysis.md` 中 decision match ≥ 30 / 32（93%+），degrade count ≤ 4。

### P6: 5 gate + 收口

- typecheck 全包绿
- lint 0 警
- 全量测试 262+ / 1700+ pass（无 regression）
- 35 scenarios 录音 35/35 pass
- 无新 degrade case
- commit + 推 origin main
- 本文 §6 commit hash + 验证结果行

## 6. 完成记录

| Pri | Status | Commit | 验证 |
| --- | --- | --- | --- |
| **P1** | ✅ | `eb49a443 fix(runtime): explicit clarification reply on loop exhaustion` | RED→GREEN→REFACTOR TDD; 14/14 unit + 35/35 acceptance + lint 0 |
| **P2** | ✅ 选项 3 | `9871c417 feat(system-prompt): read_file-first guidance` | 决策 doc `v5-real-llm-over-trigger-decision-2026-09.md`；A10/C10 修；decision match 72→81%；latency -29%；baseline /tmp/recordings-pre-read_file-first-fix |
| P3 | ⬜ | — | 待启 |
| P4 | ⬜ | — | 待启 |
| P5 | ⬜ | — | 待启（PRD P5 = 重跑 35 录音，P2 已部分完成此步骤）|
| P6 | ⬜ | — | 待启 |

## 7. Claude Code 接手步骤

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git status && git log --oneline -3   # 确认在 main 8382d258
# P1 入口：packages/runtime/src/conversation-loop.ts loop exhausted 分支
# P2 入口：docs/plans/decisions/v5-real-llm-over-trigger-decision-2026-09.md (新)
# P3 入口：packages/adapters/src/llm-decoder.ts decodeDecision 重试分支
# P4 入口：packages/runtime/src/conversation-loop.ts tool name 白名单

# 重录音：
pnpm exec tsx --env-file=.env.local scripts/acceptance/record-real-llm.ts

# Diff：
pnpm exec tsx /tmp/diff-real-llm.ts   # 详见对话记录

# 5 gate：
CI=true pnpm test
pnpm lint
```

> ⚠️ 本 PRD 不修 fixture — fixture 是验收 target，反映 v5 设计意图。如评估认为 fixture 偏松（P2），决策记录后另开 ADR。