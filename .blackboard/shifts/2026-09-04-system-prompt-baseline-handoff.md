# 系统 prompt baseline + 产品层 gap 收口交接卡

> 时间：2026-09-04 · main `d3b3478a` · 前置：D43.1 (2026-09-02) · 收口：v5 production-ready 等业主手试

## 一句话

Post-D43 阶段三条产品层 gap 全 ship (P0 inline-approval emoji + P1 read-only run_command + P1+P2 usage/undo/spam)，系统 prompt 加 B1 owner context + reply-style + take-action bias 三层建立 baseline，35 真实场景 acceptance harness 上线，等业主 1 周手试后启动下一批。

## 并入内容（d3b3478a..4972ed94，main +12 commits）

### 产品层 gap 闭环（35 场景分析 → 6 gap 修 3 留 3）

| gap | commit | 修法 |
| --- | --- | --- |
| 🔴 P0: inline-approval 不识别 `y`/`👌` | `69dc924c` | `apps/api/src/runtime/inline-approval.ts` intent match 加 y/n/emoji 👌/✅/👍/❌/👎 |
| 🟠 P1: read-only run_command 走 approval | `d226f33f` | domain 层 `executeRunCommand` 按 read-only prefix 跳过 policy gate |
| 🟠 P1: 使用率埋点 | `46ef4db3` | capability telemetry record → audit event；零性能开销 |
| 🟡 P2: /undo 空承诺 | `46ef4db3` | wechat inbound `/undo` 真撤销 last action + audit |
| 🟡 P2: 长消息 spam | `46ef4db3` | inbound rate-limit + 重复内容抑制 |

3 留待：真实 LLM 回放（需 `MINIMAX_API_KEY`）/ 个别边缘 case 待业主撞问题触发。

### 系统 prompt 三层 baseline（3 轮录音对比实证）

| 层 | commit | 录音对比（baseline → +B1 → +reply-style） |
| --- | --- | --- |
| B1 owner + workspace context | `1b4d615d` | "v5 是什么" 3 问 → 真实项目知识注入 |
| A2/A8/D5 reply-style + take-action | `d3b3478a` | toolCalls 6→2 (probing→concise), replyLen 639→197 chars (-69%), latency 15.7s→7.7s (-51%) |
| 总延迟 | — | 341s → 253s (-26%) |

### Acceptance 基础设施

| 项 | commit | 用途 |
| --- | --- | --- |
| 11 用例 acceptance harness | `4972ed94` | 跨重启 PGlite + 每用例独立 conversationId |
| 35 realistic owner-task scenarios | `aadf23ce` | 产品层行为分析（mocked LLM fixture） |
| Real-LLM recording script | `534cccee` | 业主跑：MINIMAX_API_KEY=true → 录真实轨迹 |

## 5-gate（S1 复核）

- lint apps：**0 警** ✅
- 全量 `CI= pnpm test`：253 files / ~1545 pass / 1 skip（与 D49 一致；S6 baseline 同 2 环境已知 fail） ✅
- baseline `_analyze.md`：本次会话末重跑 acceptance 触发 9 UUID 漂移（artifact-only，无语义变化），已 `git checkout` 丢弃 ✅
- 主干状态：working tree clean ✅

## Baseline 沉淀

- `recordings/` （gitignored）→ 第 3 轮 = v5 当前真实 LLM baseline
- `/tmp/recordings-pre-style-fix` → 第 2 轮 +B1 对比基线
- `/tmp/recordings-pre-context-fix` → 第 1 轮原 B1 状态

## S1 待办 / 提示

- ⚠️ **D49 遗留 typecheck 仍未清**：`apps/api/wechat-project-surface.ts:314` exactOptionalPropertyTypes（S6 已承认未修，S1 待业主决策是否顺手修）。
- ⚠️ **D35/D36 DESIGN placeholder dates** L617/L618 仍未刷；非阻塞，等下个 doc pass。
- 业主手试起点：`pnpm test` → 撞真实使用问题 → 重跑 `recordings/` 录音对比 → 触发下一批。
- 系统 prompt 改动流程已立 baseline：每改 system prompt / fixture / 工具，重跑 35 场景 ≈ 4 分钟 vs 之前凭直觉改。

## 提醒

- 系统 prompt 改动需重跑 35 场景 + 比对录音（baseline 在 `recordings/`）；4 分钟成本 = 唯一防退化机制。
- `recordings/` gitignored — 不可 commit；丢失意味着下一轮对比基线要重录。
- 下一批 trigger：业主真撞产品问题（最可能：使用率数据暴露的频繁 fail 路径 / 真实 LLM 回放发现的模型差异）。