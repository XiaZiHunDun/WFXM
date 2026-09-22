# Butler v5 — Project Feedback Lessons Index

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計; D80 梳理 +22 ship = 149) | **读者**: 新 session agent / next-cycle 启动者
> **关系**:
> - 功能清单 → [`FEATURES.md`](FEATURES.md)
> - API / env / tests / audit findings / 工程治理 → [`API_ENDPOINTS.md`](API_ENDPOINTS.md), [`ENV.md`](ENV.md), [`TESTS.md`](TESTS.md), [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md)
> - 工程治理梳理 → [`../AGENTS.md`](../AGENTS.md) + `.cursorrules` + `.blackboard/state.md`
> - 完整 lessons → `.claude/projects/.../memory/feedback-*.md` + `project-*.md`（user home / project-local；gitignored）
> - D-series 累計 → [`ROADMAP.md`](ROADMAP.md)

> **范围**: 本表聚合 **18 feedback lessons**（11 user-home + 2 project-local + 5 v8 PRD findings）。每条含 **Context / Problem / Solution / How to apply / Why**，按类别聚类。

---

## §0 总览

| 类别 | 数量 | 主旨 |
|------|------|------|
| §1 Communication & Handoff | 3 | 中文 / 1 句话 / push-to-main |
| §2 Documentation & Spec | 3 | 顶部日期 / framework / scope |
| §3 Git & Bash | 2 | 反引号 / pre-commit hook |
| §4 D-series Cycle | 5 | reply-string batch / plan import / raw-findings / archived / hook retire |
| §5 V8 PRD Real LLM Findings | 5 | fixture / policy / over-clarification / temperature / recordings |
| §6 Engineering Tooling | 1 | ts-prune false positive |
| **Total** | **19 lessons** | — |

## §1 Communication & Handoff

### 1.1 `feedback-language` — 中文为主

**Context**: 用户 2026-05 + 2026-07 两次要求"恢复中文对话"；"机械延续"惯性是默认英文最大风险点。

**Rule**: 在 WFXM 项目下**默认用中文回复**（标题、说明、状态汇报、收尾），但保留以下英文：
- 标识符（函数名、变量名、类名、文件路径、git commit hash）
- 审计编号（audit 5.1.x）
- 测试断言里的字面字符串
- Git 提交标题里的类型前缀（`fix:` `feat:` 等）
- 用户主动切换为英文时跟随其选择
- **强提醒**：哪怕是「已完成 / 已推送」这种一行收尾也必须中文。

**Source**: `.claude/projects/.../memory/feedback-language.md`

### 1.2 `feedback-handoff-discipline` — 1 句话给选项

**Context**: 2026-06-06 PR-2 收尾 — 跑 `which gh` 一次没看到就 draft 30-line PR body + clickable URL；用户反馈"我没太明白你为什么需要我做这个"。

**Rule**: 接活结束需要 user 操作时（如"create PR / open browser / run command X"），1 句话给选项：
1. **Do it yourself** — 穷尽 3 路径检查（CLI / MCP / env var）。MCP server list 在 `~/.claude.json`（不是 `~/.claude/mcp-configs/mcp-servers.json` 模板）。
2. **If you truly cannot** — 1 句话："I tried gh, GITHUB_TOKEN, MCP github server (token=placeholder) — none usable. Options: [A] [B] [C]". 不要 pre-draft 整个 handoff payload。

**Source**: `feedback-handoff-discipline.md`

### 1.3 `feedback-wfxm-push-to-main` — push origin/main 默认

**Context**: 2026-09-08 D45 推送后用户明确确认 "该 commit 已经在 main 上，且这个仓库前几批都是这么走的。以后如果你想让我改用 feature branch + PR，跟我说一声。"

**Rule**: 默认 `git push origin main`。**只有**用户显式说 "feature branch" / "PR" 才改路径。开 plan 时**不要**自动引入 PR 工作流。

**Source**: `feedback-wfxm-push-to-main.md`

## §2 Documentation & Spec

### 2.1 `feedback-doc-date-staleness` — 顶部日期非 mtime

**Context**: 2026-07-13 文档整理 C 批讨论 — mtime 改动的文档 30+ 个但顶部日期停在 5-6 月。用户选"跳过 C 批"而非"批量刷"。

**Rule**: 看到文档"顶部更新日期陈旧"时：
1. 不要默认提议"批量刷"
2. 先查 mtime vs 顶部日期 vs 实际内容改动
3. `git log --follow` 已给出答案，不必刷
4. 真正需要改时逐个手动验证再刷

**Source**: `feedback-doc-date-staleness.md`

### 2.2 `feedback-spec-framework-and-butler-ignore` — hook 类先 framework

**Context**: P1#4 教训 — 写 hook spec 时假设 `.claude/settings.json` PreToolUse 直接接 Python 脚本；实际 `butler/hooks/` 已有完整 framework（loader.py + runner.py + telemetry.py + hooks.yaml.example），正确做法是注册到 `<project>/.butler/hooks.yaml`。

**Rule**:
1. **写任何 hook / dispatcher / runner 类 spec 前**，必先 `ls butler/<相关>/` 确认是否有现成 framework
2. **`projects/*/.butler/` 整目录 gitignore**（`.gitignore` 第 39 行），不是单独文件 ignore。任何"要入仓的项目配置"必须放 `projects/<slug>/config/` 或其他 tracked 路径

**Source**: `feedback-spec-framework-and-butler-ignore.md`

### 2.3 `feedback-channel-trigger-scope` — channel 接活先问 scope

**Context**: R14 Slack 案例 — Owner 自报 ≠ 默认 real integration。可能是 (a) real integration / (b) structural alignment / (c) experimental PoC。

**Rule**: 接活前先问 scope（1 句话 + 给选项）：
- (a) 走完整 per-channel PRD 模板（5 项 production-ready bar）+ ADR §7 status `in-progress` → `completed`
- (b) PRD §1+§2 显式标 "structural alignment scope only"；adapter move + 单测 + 5 gate 闭环；不启动 owner 真实 e2e
- (c) PRD 走 experimental scope；不进 active；不写 ADR §7 行

**永远不假设**（per `feedback-handoff-discipline`：失败时 1 句话给选项）。

**Source**: `feedback-channel-trigger-scope.md`

## §3 Git & Bash

### 3.1 `feedback-bash-backtick-in-commit-message` — single quote

**Context**: R13 session — `git commit -m "...3 commits \`abc1234\`..."` 把 3 个反引号包住的 commit SHA 当 `$()` command substitution 执行；3 个 "command not found" 报错；commit 进程仍 exit 0 并写入损坏 body。

**Rule**:
- **修法 1（最稳）**：用 single quote 包整条 message
- **修法 2**：用 `printf` 或 here-doc (`-F -`)
- **验证**：commit 后立刻 `git log -1 --format='%B'` 看 body 是否完整；有 `/ / ` 占位说明 body 被吃了
- **如果已经 push**：amend + `git push --force-with-lease`（**不是 `--force`**）

**正例**:
```git
git commit -m 'fix: foo (commit abc1234)'  # single quote + 无内层反引号
git commit -m "fix: foo (commit abc1234)"   # 不带 backtick，直接括号
```

**Source**: `feedback-bash-backtick-in-commit-message.md`

### 3.2 `feedback-precommit-hook-flakiness` — ROOT 计算 bug

**Context**: WFXM pre-commit hook (`scripts/ai_guard/pre_commit_hook.sh`) 间歇性误报 protected entry。R7.5 闭环时钉死根因：hook 第 17 行 `ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"` — git 用绝对路径调 hook 时 `dirname/..` = `.git/`（不是 repo 根）；`GIT_INDEX_FILE=.git/index` 配 phantom index 产生 4651 路径垃圾。

**Rule**:
- **新 commit（普通改动）**：`git commit -m "..."`，hook 应正常通过
- **如被 BLOCKED，先确认 staged 里有没有真受保护文件**：`git diff --cached --name-only | grep -E "^butler/core/agent_loop/loop\.py$|^pyproject\.toml$|^\.claude/settings\.json$|^scripts/ai_guard/(pre|post)_tool_use_hook\.py$"`；空就是 hook 误报
- 真要改 protected 文件 → commit message 加 `[MANUAL-OVERRIDE]`（hook 检测到就放行）
- 验证 hook 与源同步：`diff -q scripts/ai_guard/pre_commit_hook.sh .git/hooks/pre-commit` 应为空

**Source**: `feedback-precommit-hook-flakiness.md`（**已修**：R8.3 commit `89635374`，ROOT 改成 `cd "$(dirname)/../.."`）

## §4 D-series Cycle Discipline

### 4.1 `feedback-d-batch-reply-string-test-update-batch` — reply 同 batch 改测试

**Context**: D63 audit cycle #9 (2026-09-13) T2 owner-jargon 5th sweep shipped 10 sites 改 reply string。T2 reply-string changes broke **38 acceptance tests** across 5+ test files。

**Rule**: D-batch 改 owner-facing reply string (owner-jargon / inline-approval / run-notify) MUST include test updates in same batch — 否则 30+ acceptance tests break across realistic / product-regressions / commands-approval / fault-tolerance / subagent-multiturn。

**Solution**:
1. Before shipping reply-string changes，audit acceptance test files for exact string assertions
2. For each changed string，find the corresponding test assertion and update in same commit
3. Ship code + tests together

**D63 选择 option 2 (revert 7 sites from T2, defer to D64+)**；D64+ ship owner-jargon 5th sweep remainder with test updates in same batch.

**Source**: `feedback-d-batch-reply-string-test-update-batch.md`

### 4.2 `feedback-plan-import-vs-arch-boundary` — plan cross-package vs §3

**Context**: Plan task template (D40 G1 Task 3) 说 `import type { DurableMemoryStore } from "@butler/persistence/durable-memory-store.js"` inside `packages/domain/`。persistence's `package.json` exports map 不列 `./durable-memory-store.js`；domain 无 `@butler/persistence` 依赖（per §3 #1）；TS2307 报错。

**Rule**:
- Define minimal local interface in domain capturing only methods the pure fn uses (TypeScript structural typing)
- Verification before typing import:
  ```bash
  ls butler-v5/packages/<own-package>/node_modules/@butler/ 2>/dev/null
  # If empty → no cross-package imports allowed
  ```
- 与 `RuntimeStore` 同 pattern（defined in domain/runtime/store-contract.ts）

**Source**: `feedback-plan-import-vs-arch-boundary.md`

### 4.3 `feedback-audit-raw-findings-must-archive` — D57 lesson #1

**Context**: D56 raw findings (71 项) 没存盘 → D57 必须 fresh 3-sub-track audit 重跑。浪费 audit protocol reuse 优势。

**Rule**: 每次 audit-driven fix batch 完成后：
1. 写 ship batch memo (`project-fix-DXX-audit-driven-fixes-yyyy-mm-dd.md`)
2. **新增**: 单独写 raw findings JSON (`project-audit-DXX-raw-findings-yyyy-mm-dd.md`) 到 memory/
3. raw findings 文件 ship 时同时存在 batch memo 里能 cross-link (Plan A → F-XX → commit SHA)
4. 下次 audit-driven batch 第一步: Read 上次 raw findings → diff vs fresh audit → 决定 ship scope

**不要**: 把 raw findings 只放在 chat history / context window 里；下 session 不可见。

**Source**: `feedback-audit-raw-findings-must-archive.md`

### 4.4 `feedback-archived-test-rot-pattern` — archived test Die root cause

**Context**: archived Effect v3 test Dies with "Not a valid effect: undefined"。根因：Tag supposed via Layer，但 plain object wrongly passed to `Layer.mergeAll(...)`。

**3-step check**:
- (a) grep failing test for `Layer.mergeAll` arguments — confirm every arg is a `Layer<...>` (not a plain config / data object)
- (b) For each Tag the `Effect.gen` body `yield* _()`s, verify the test provides a `Layer.succeed(Tag, ...)` or proper mock Layer
- (c) `pnpm exec tsx /tmp/repro.mts` with minimal repro — confirms missing Layer, not API rot

**Fix shape**: `Layer.mergeAll(M1, M2, ..., Layer.succeed(Config, makeTestConfig()))`. Import `Config` from `@butler/ports`.

**Source**: `feedback-archived-test-rot-pattern.md`

### 4.5 `feedback-v5-ai-guard-protected-files` — R17 hook 退役

**Context**: R17 (2026-08-28) 评估反转本 memory 论点。v5 项目 AI 守卫**已退役**。DESIGN §19 明文：hooks 是工程治理，**不属于产品运行时架构**。

**Rule**:
- **不要**提议"修 hook"或"暂时去掉 protected"（hook 已退役）
- **不要**写"hook 永久存在"作为不可变约束
- R-* plan 阶段**第一 SOP 步骤**仍是 `grep -nE "PROTECTED_FILES|AI 守卫" CONTRIBUTING.md .cursorrules butler-v5/AGENTS.md 2>/dev/null`（验证"承重"标记仍准确）
- 涉及"承重"文件改动时，主动跑 5 gate + 详细 review

**保留**（非 hook，是 CI/git 机制）：
- `scripts/ai_guard/file_size_check.py` — CI gate + local gate
- `scripts/ai_guard/pre_commit_hook.sh` + `.git/hooks/pre-commit` — git pre-commit

**Source**: `feedback-v5-ai-guard-protected-files.md`

## §5 V8 PRD Real LLM Findings

> 5 lessons 全部从 2026-09-07 V8 PRD 3/3 candidate revert 实证。

### 5.1 `feedback-fixture-calibration-rounds-noisy-2026-09-07` — whack-a-mole

**Context**: V8 candidate A — 改 `_fixtures.ts` D3/D5 `expect.finalDecision: "WaitForApproval"` → `"Finish"` 接受 P1 loop-exhausted 实际行为。**Aggregate regression**: decision match 88%→78% / approval match 33→30 / latency 178s→224s。

**Why**: Real LLM 是 temperature 模型，跨 round 行为 noisy。D3 v7 走 Finish (loop exhausted)，v8 走 WaitForApproval (try again)；fixture 改 ≠ model 跟着改。

**Rule**:
- **不改 fixture 接受 model 行为** — fixture 是验收 target，反映 v5 设计意图
- 残余 mismatch 接受为 "model 行为超出 fixture 设计意图" 记录在 PRD 而非 fixture

**Source**: `feedback-fixture-calibration-rounds-noisy-2026-09-07.md`

### 5.2 `feedback-policy-bypass-cost-tradeoff-2026-09-07` — aggregate metrics not just target

**Context**: V8 candidate C — `isReadOnlyCommand` 加 `find` 白名单（mutating-flag 黑名单 -exec/-delete/-fprint/-ok）。D4 turn 2 fix ✓；**aggregate regression**: latency 151s→229s (+52%) / tool calls 49→65 (+33%) / 4 cases Finish fallback / D1 latency 8s→27s / D3 2s→20s。

**Rule**:
- 改 `isReadOnlyCommand` 白名单前先跑 4 分钟 harness 比 **aggregate metrics**（不只看 1 target case）
- `actual tool calls / total latency` 是模型探索程度的代理 — +30% 说明 policy 太宽
- `Finish fallback count` 是收敛失败的代理 — 若增加说明 prompt 鼓励探索但 model 不收敛
- 默认保守；扩白名单需 "block mutating flags" + "限定 maxdepth / max args" 双重护栏

**Source**: `feedback-policy-bypass-cost-tradeoff-2026-09-07.md`

### 5.3 `feedback-over-clarification-prompt-tradeoff-2026-09-07` — take-action bias

**Context**: V8 candidate B — P2 convergence prompt 后加 "Missing context: if workspace empty or file missing, do NOT loop probing — ask 1 clarifying question"。**Aggregate regression**: decision match 88%→69% / latency 178s→261s / **A2 单 case latency 11s→54s** (model 反复追问 5+ turns)。

**Rule**:
- **不在 convergence prompt 加新 ask 触发器** — 让现有 P2 take-action bias 继续生效
- 改 prompt 前必看 aggregate metrics
- "加 ask 触发器" 风险高于 "改 allow list" — 前者影响决策，后者只影响 surface
- 测试 ask 类 prompt 时：分别测 (a) ask 触发率 (b) take-action rate — 两个不能同时涨

**Source**: `feedback-over-clarification-prompt-tradeoff-2026-09-07.md`

### 5.4 `feedback-temperature-model-changes-unprovable-2026-09-07` — single round 不可靠

**Context**: V8 PRD candidate A (fixture) / B (convergence prompt) / C (tree bypass) — 3/3 都 empirical revert。Root cause: temperature model 跨 round variance 大；35 scenario 单一 snapshot 不能区分 "prompt 改对了" vs "model variance"。

**Rule**:
- 单 round 35 scenario 不足以验证 LLM-related change
- 需要：(1) N round (e.g., 3) 录音取 avg metrics 减 variance；(2) 或保持 fix + 量 cost/latency impact 间接证；(3) 或等 owner hand-trial 真问题触发（最稳）
- 改 system prompt / fixture / policy 前必须有真实 user problem trigger，否则修不能验证

**当前 PRD V8 4 candidates 3/3 revert**：仅剩候选 D（等 owner hand-trial）值得做。

**Source**: `feedback-temperature-model-changes-unprovable-2026-09-07.md`

### 5.5 `feedback-recordings-rotation-baseline-2026-09-04` — 4 分钟 harness baseline

**Context**: v5 系统 prompt / fixture / 工具持续演化；35 场景 acceptance harness 是唯一 4 分钟内跑完的实证。`recordings/` 第 3 轮 = 当前真实 LLM baseline。

**Rule**:
- **`recordings/` (gitignored)** = 第 3 轮 baseline（v5 当前状态）— 唯一权威
- **`/tmp/recordings-pre-style-fix`** = 第 2 轮（+B1 context, 无 reply-style）
- **`/tmp/recordings-pre-context-fix`** = 第 1 轮（baseline，B1 gap 暴露）
- **4 分钟 harness 流程**：改 → `pnpm --filter @butler/api test:acceptance` → 比对 → 退化回滚
- **量化 3 维度**：toolCalls (A2 probing) / latency / replyLen (D5 mobile)
- 退化判定：toolCalls +2 / latency +2s / replyLen +30% 任一触发 → 回滚 prompt
- recordings/ 目录若不存在 = 上轮 baseline 丢失 → 立刻跑 1 次 mock + 1 次 MINIMAX 重建

**Source**: `feedback-recordings-rotation-baseline-2026-09-04.md`

## §6 Engineering Tooling

### 6.1 `feedback-ts-prune-cross-package-false-positive` — knip 替代

**Context**: 2026-09-04 — `pnpm deadcode` (`ts-prune packages/ apps/ --error`) 产出 784 行"dead" candidates。深度 sample 验证后绝大多数是 false positive。

**Why**: ts-prune 不会跨包追踪 re-export chain；它只看 `import { X } from "./same-file"` + 直接 `from "package/file"`。barrel pattern（`packages/*/src/index.ts` 集中 re-export）下，源文件的 export 实际被 `@butler/runtime` 消费，ts-prune 看不到这条链。

**Rule**:
- 单包范围 ts-prune 可信（不出 index.ts）
- **跨包**结论前必须人工 sample 几个 candidate：是否在 `index.ts` re-export？该 re-export 名称在其他包的 import 语句出现？
- 装 knip（`pnpm add -D knip`）— 设计上追踪 cross-package re-export，monorepo 推荐
- 或干脆接受 deadcode "PASS" 现状，依赖 typecheck + lint + 全量回归 + 真实覆盖 + 长期 review catch 真死代码

**复现证据**: `LLMMessage` / `LLMTool` / `LLMAdapter`（`@butler/adapters`）、`defaultWechatConversationId` / `parseClientConversationId`（`@butler/runtime/intake`）— 全部 ts-prune 报"unused"，实际是 acceptance harness 必需的 runtime API。

**Source**: `feedback-ts-prune-cross-package-false-positive.md`（D53b 已 ship `pnpm knip` 替代）

## §7 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单 | [`FEATURES.md`](FEATURES.md) |
| API endpoint | [`API_ENDPOINTS.md`](API_ENDPOINTS.md) |
| env vars | [`ENV.md`](ENV.md) |
| 测试覆盖 | [`TESTS.md`](TESTS.md) |
| TODO / deferral | [`TODO_DEFERRED.md`](TODO_DEFERRED.md) |
| Audit findings | [`AUDIT_FINDINGS.md`](AUDIT_FINDINGS.md) |
| 工程治理入口 | [`../AGENTS.md`](../AGENTS.md) + `.cursorrules` + `.blackboard/state.md` |
| 完整 lessons（gitignored） | `.claude/projects/.../memory/feedback-*.md` + `project-*.md` |
| D-series 累計 | [`ROADMAP.md`](ROADMAP.md) |
| Owner FAQ（D-series / audit-driven / 节奏判据） | [`FAQ.md`](FAQ.md) |

---

**End of FEEDBACK.md** | D80 cycle 26 inventory batch | **19 feedback lessons / 6 categories**（Communication / Docs / Git / D-series / V8 PRD / Tooling）