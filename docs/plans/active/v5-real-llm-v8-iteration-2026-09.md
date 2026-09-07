# v5 真 LLM Iteration v8 预备 PRD（基于 v7 diff 残余 mismatch）

> **状态**：Active planning（候选项，待 owner 触发或下批审阅）
> **触发**：v7-current recording baseline（HEAD `1252143c`）diff baseline 显示 5 case 残余 mismatch — 不是 bug 修复列表，是 candidate iteration
> **目的**：文档化 v8 candidate changes + rotation policy 锚定；按 4 步反查协议评估哪个真该写
> **完成归档**：每 candidate 实施后 commit 落本文 §4 行

## 1. 背景

v7-current（HEAD `1252143c`）35 录音 diff fixture：

| 维度 | 当前 |
| --- | --- |
| decision match | **28/32 (88%)** |
| total latency | 178s |
| unknown tool warnings | 0 |
| A10/C10/A9/D4(both turns) | fixed |
| D1 loop exhausted | clarification reply (PRD P1) |

剩余 5 case mismatch 不是退化，是 v5 模型超越 fixture 设计意图 或 fixture 已 stale：

## 2. v7 diff 残余 mismatch（候选迭代点）

| # | ID | Fixture | Actual | 候选方向 |
| --- | --- | --- | --- | --- |
| 1 | **A5** | WaitForApproval 批 `foo.ts` 删 import | Respond "目录是空的" | (a) fixture 改 Respond 接受 model 更准 (b) prompt 加 "找不到文件 → 主动 ask 路径" |
| 2 | **C8** | WaitForApproval 批写文件 | Respond "你想写什么？" | (a) fixture 改 Respond (b) prompt 加 "用户意图不清 → ask 1 个澄清问题" |
| 3 | **D3** | WaitForApproval 批 user.ts | Finish (loop exhausted, P1 fix in action) | fixture stale — D3 fixture 期望写 user.ts 但 workspace empty → 5 iter 内不收敛。**fixture 改 Finish** 是最简 fix |
| 4 | **D5** | WaitForApproval 批 /debug 命令 | Finish (loop exhausted) | 同 D3 — fixture stale |
| 5 | **D1** | WaitForApproval 批 helper 测试 | WaitForApproval ✓ (但 apprMatch = ✗ 因为 finish-approval 路径分歧) | fixture 微调 |

注：A5/C8 是 model 行为比 fixture 设计意图更稳。**D3/D5 是 fixture stale relative to P1 fix**（v5 PRD P1 把 loop-exhausted 改成 Finish 而非 WaitForApproval）。

## 3. v8 candidate changes（按 ROI 排序）

### 候选 A — Fixture 校准 (低风险, 高 ROI)

**改动**：A5/C8/D3/D5 fixture 改 Respond 或 Finish 接受 model 实际行为
**范围**：`_fixtures.ts` 4 case expect 调整
**Gate**：35 scenarios mock pass + 35 real LLM re-record vs v7-current baseline
**验收**：decision match ≥ 30/32 (94%) by accepting model quality；不引入新 degrade
**风险**：fixture 降低严格度 — 与"fixture 是验收 target"原则冲突。仅在 model 行为客观优于 fixture 设计意图时接受。

### 候选 B — Convergence prompt 加固（中风险, 中 ROI）

**改动**：在 P2 已加的 "Convergence: 1-2 file-discovery → commit plan" 后加 "如 workspace 空 → 主动 ask 1 个澄清问题"
**范围**：`apps/api/src/wechat-inbound-llm.ts` + 1 test
**Gate**：35 scenarios re-record vs v7-current
**验收**：A5/C8 mismatch → match；D3/D5 仍 Finish（行为不变）；latency 不增 >5%
**风险**：over-clarification 可能让 model 变得太保守，反削弱 P2 的 take-action bias

### 候选 C — Read-only bypass 扩 wsat (低风险, 低 ROI)

**改动**：`isReadOnlyCommand` 加 `wsat` 进 ALWAYS_READONLY
**范围**：`packages/domain/src/governance/types.ts` + 1 test
**Gate**：35 scenarios re-record vs v7-current
**验收**：wsat 不再触发 approval；其他 case 无 regression
**风险**：无（read-only 单字程序，无 subcommand）

### 候选 D — Owner hand-trial 反馈循环

**改动**：无主动代码改动；等 owner 手试 1 周 → 撞真问题 → 触发下批 PRD
**范围**：MEMORY.md 持续记录
**Gate**：以 owner 撞问题为 trigger
**验收**：N/A
**风险**：等待时间未知

## 4. 4 步反查协议（沿用 [[project-deferred-trigger-conditions-2026-09-01]]）

| Step | 检查 | v8 candidate |
| --- | --- | --- |
| 1. 真问题？ | owner 撞过吗？ | 候选 A 4 fixture stale 是客观事实；B/C/D 是 hypothetical |
| 2. 真 ROI？ | 改 vs 不改 哪个好 | A ROI 高（fixture 调整无 code 改）；B 中；C 低；D 等待 |
| 3. 真时机？ | 现在改 还是 等？ | A 可立即做（fixture 校准无 user 风险）；B/C 等下批 |
| 4. 真 ownership？ | 谁负责？ | A：Claude（owner review）；B：Claude 起草 + owner prompt review；C：Claude；D：owner |

**推荐顺序**：A 先做（fixture 校准，低风险）→ D 等待 owner feedback → 后续 B/C 视手试反馈决定。

## 5. Rotation policy 锚定（v7-current README 引用）

每 v8+ candidate 实施前：

```bash
# 1. Snapshot current (已在 recordings-archive/v7-current)
cp -r butler-v5/tests/acceptance/scenarios/recordings-archive/v7-current \
      butler-v5/tests/acceptance/scenarios/recordings-archive/v8-pre-{candidate-name}-fix

# 2. Apply candidate + re-record (35 scenarios, ~4 min)
cd butler-v5
pnpm exec tsx --env-file=.env.local scripts/acceptance/record-real-llm.ts
cp -r tests/acceptance/scenarios/recordings \
      butler-v5/tests/acceptance/scenarios/recordings-archive/v8-current

# 3. Diff vs v7 baseline
pnpm exec tsx /tmp/diff-real-llm.ts

# 4. Aggregate metrics gate — only commit if improve
# - decision match ≥ v7 (≥28/32)
# - latency ≤ v7 + 10% (≤196s)
# - unknown tool warnings = 0
# - 其他 case 无 regression
```

## 6. 完成记录

<!-- 落地后增 -->

## 7. Claude Code 接手步骤

```bash
cd /home/ailearn/projects/WFXM/butler-v5

# 当前 v7 baseline 状态
git status && git log --oneline -3   # 确认在 main 1252143c

# 看 v7 diff 残余 mismatch
pnpm exec tsx /tmp/diff-real-llm.ts | grep "✗"

# 启动 v8 candidate：
# - 候选 A: edit _fixtures.ts A5/C8/D3/D5 expect 段
# - 候选 B: edit apps/api/src/wechat-inbound-llm.ts 加 convergence 续行
# - 候选 C: edit packages/domain/src/governance/types.ts ALWAYS_READONLY 加 "wsat"
# - 候选 D: 等 owner hand-trial 1 周
```

> ⚠️ 本 PRD 是 planning shell — 每个 candidate 单独 TDD (RED → GREEN → REFACTOR) + 4 分钟 harness 比 aggregate metrics，按 §5 rotation policy。不批量 commit 多个 candidate。